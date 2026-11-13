"""Re-apply the HellHades "sell/equip in game" fix after HellHades updates.

HellHades opens RAID with OpenProcess(VM_OPERATION|VM_READ|VM_WRITE) and then
calls CreateRemoteThread on that handle to load its helper. Without
PROCESS_CREATE_THREAD (0x2) this fails with ERROR_ACCESS_DENIED ("Failed to
create remote thread in RAID to load helper"). This script finds every call to
the OpenProcess P/Invoke in HellHades.ArtifactExtractor.Models.Reader.dll by
reading the .NET metadata (so it does not depend on byte offsets, which change
every build) and adds CREATE_THREAD to the access constant passed to it.

Safe to run any time: it is a no-op if the DLL is already fixed, keeps the
unpatched original as <dll>.orig, and replaces the file atomically.

    uv run python -m tools.hh_patch [HH install dir or the DLL] [-q]   # default: $HH_DIR

`just hh-patch` passes the install the justfile names (`.env`'s HH_DIR, else the default).
Exit codes: 0 ok (patched or nothing to do), 1 could not patch, 2 bad input.
"""

import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import click

DLL = "HellHades.ArtifactExtractor.Models.Reader.dll"
CREATE_THREAD, VM_OPERATION, VM_WRITE = 0x2, 0x8, 0x20


class Meta:
    """Just enough ECMA-335 metadata parsing to name MethodDef rows."""

    def __init__(self, data):
        self.data = data
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe : pe + 4] != b"PE\0\0":
            raise ValueError("not a PE file")

        nsec, optsz = (
            struct.unpack_from("<H", data, pe + 6)[0],
            struct.unpack_from("<H", data, pe + 20)[0],
        )
        opt = pe + 24
        ddir = opt + (96 if struct.unpack_from("<H", data, opt)[0] == 0x10B else 112)
        clr_rva = struct.unpack_from("<I", data, ddir + 14 * 8)[0]
        self.sections = []

        for i in range(nsec):
            header = opt + optsz + 40 * i
            vsize, va, rawsize, raw = struct.unpack_from("<IIII", data, header + 8)
            self.sections.append((va, max(vsize, rawsize), raw))

        if not clr_rva:
            raise ValueError("not a .NET assembly")

        md = self.off(struct.unpack_from("<I", data, self.off(clr_rva) + 8)[0])
        if struct.unpack_from("<I", data, md)[0] != 0x424A5342:
            raise ValueError("bad metadata signature")

        vlen = struct.unpack_from("<I", data, md + 12)[0]
        pos = md + 16 + vlen + 2
        nstreams = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        streams = {}

        for _ in range(nstreams):
            offset, size = struct.unpack_from("<II", data, pos)
            end = data.index(b"\0", pos + 8)
            streams[data[pos + 8 : end].decode()] = (md + offset, size)
            pos = pos + 8 + ((end - (pos + 8)) // 4 + 1) * 4

        self.strings = streams["#Strings"][0]
        tables = streams.get("#~") or streams.get("#-")
        if not tables or "#Strings" not in streams:
            raise ValueError("metadata tables stream missing")

        tables_at = tables[0]
        heap = data[tables_at + 6]
        self.si, gi, bi = (4 if heap & 1 else 2), (4 if heap & 2 else 2), (4 if heap & 4 else 2)
        valid = struct.unpack_from("<Q", data, tables_at + 8)[0]
        rows, pos = [0] * 64, tables_at + 24

        for i in range(64):
            if valid >> i & 1:
                rows[i] = struct.unpack_from("<I", data, pos)[0]
                pos += 4

        if heap & 0x20:  # extra data (uncompressed #- streams)
            pos += 4

        def idx(tbl):
            return 4 if rows[tbl] > 0xFFFF else 2

        def coded(tbls, bits):
            return 4 if max(rows[x] for x in tbls) >= 1 << (16 - bits) else 2

        si = self.si
        sizes = [
            2 + si + 3 * gi,  # 0 Module
            coded([0, 0x1A, 0x23, 1], 2) + 2 * si,  # 1 TypeRef
            4 + 2 * si + coded([2, 1, 0x1B], 2) + idx(4) + idx(6),  # 2 TypeDef
            idx(4),  # 3 FieldPtr
            2 + si + bi,  # 4 Field
            idx(6),  # 5 MethodPtr
        ]
        for tbl, size in enumerate(sizes):
            pos += rows[tbl] * size

        self.mdef, self.mdef_rows = pos, rows[6]
        self.mdef_size = 8 + si + bi + idx(8)

    def off(self, rva):
        for va, size, raw in self.sections:
            if va <= rva < va + size:
                return rva - va + raw

        raise ValueError(f"RVA {rva:#x} outside sections")

    def method(self, row):
        """(name, flags) of MethodDef row (1-based)."""
        if not 1 <= row <= self.mdef_rows:
            return None, 0

        row_at = self.mdef + (row - 1) * self.mdef_size
        flags = struct.unpack_from("<H", self.data, row_at + 6)[0]
        name = struct.unpack_from("<I" if self.si == 4 else "<H", self.data, row_at + 8)[0]
        name_at = self.strings + name
        return (
            self.data[name_at : self.data.index(b"\0", name_at)].decode("utf-8", "replace"),
            flags,
        )


def find_sites(data, meta):
    """Yield (offset, width, value) of the access constant of each OpenProcess call."""
    for match in re.finditer(rb"\x28(...)\x06", data, re.S):  # call <MethodDef token>
        row = int.from_bytes(match.group(1), "little")
        name, flags = meta.method(row)
        if name != "OpenProcess" or not flags & 0x2000:  # must be the P/Invoke
            continue

        call = match.start()
        # IL pushes (access, inherit, pid): look back for "ldc access; ldc.i4.0/1"
        best = None

        for pos in range(call - 1, max(call - 48, 0), -1):
            if data[pos] == 0x1F and data[pos + 2] in (0x16, 0x17):  # ldc.i4.s imm8
                best = (pos + 1, 1, data[pos + 1])
            elif data[pos] == 0x20 and data[pos + 5] in (0x16, 0x17):  # ldc.i4 imm32
                best = (pos + 1, 4, struct.unpack_from("<i", data, pos + 1)[0])

            if best:
                break

        yield call, best


def notify(msg):
    print(msg, file=sys.stderr)

    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        subprocess.run(
            ["notify-send", "-a", "HellHades patch", "HellHades patch", msg],
            stderr=subprocess.DEVNULL,
            check=False,
        )


@click.command(help=__doc__)
@click.argument("target", envvar="HH_DIR", type=click.Path(path_type=Path))
@click.option("-q", "--quiet", is_flag=True, help="Say nothing when there is nothing to do.")
def main(target: Path, quiet: bool) -> None:
    sys.exit(patch(target, quiet))


def patch(target: Path, quiet: bool) -> int:
    """Patch the Reader DLL (`target`, or in the install dir `target`); the exit code."""
    path = str(target / DLL if target.is_dir() else target)

    if not os.path.isfile(path):
        notify(f"no HellHades Reader DLL at {path}")
        return 2

    try:
        data = bytearray(open(path, "rb").read())
        meta = Meta(bytes(data))
    except (OSError, ValueError, KeyError, IndexError, struct.error) as e:
        notify(f"cannot read {path}: {e}")
        return 2

    sites = list(find_sites(bytes(data), meta))
    if not sites:
        notify("no OpenProcess call found in HellHades; layout changed, sell/equip may fail")
        return 1

    changed, problems = [], []

    for call, site in sites:
        if site is None:
            problems.append(f"call at {call:#x}: access constant not found")
            continue

        offset, width, val = site
        if val & CREATE_THREAD or (val & (VM_OPERATION | VM_WRITE)) != VM_OPERATION | VM_WRITE:
            continue  # already fine, or a read-only handle that never injects

        new = val | CREATE_THREAD

        if width == 1:
            data[offset] = new
        else:
            struct.pack_into("<i", data, offset, new)

        changed.append(f"{call:#x}: {val:#x} -> {new:#x}")

    if problems:
        notify("; ".join(problems))

    if not changed:
        if not quiet:
            print("already patched (or fixed upstream); nothing to do")

        return 1 if problems else 0

    orig = path + ".orig"
    shutil.copy2(path, orig)  # the current file is unpatched: keep it as the original
    tmp = path + ".patching"
    with open(tmp, "wb") as out:
        out.write(data)

    shutil.copystat(path, tmp)
    os.replace(tmp, path)
    print("patched OpenProcess access at " + ", ".join(changed))
    return 1 if problems else 0


if __name__ == "__main__":
    main()
