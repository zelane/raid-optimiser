#!/usr/bin/env python3
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

    hh-patch.py <prefix id> [-q]     # the Steam compatdata id of RAID's Proton prefix
    hh-patch.py <path to dll> [-q]

The DLL is looked for in the prefix's HellHades install: AppData/Roaming (the installer's
place), then drive_c/hh.
Exit codes: 0 ok (patched or nothing to do), 1 could not patch, 2 bad input.
"""
import os, re, shutil, struct, subprocess, sys

DLL = "HellHades.ArtifactExtractor.Models.Reader.dll"
COMPATDATA = os.path.expanduser("~/.local/share/Steam/steamapps/compatdata")
INSTALLS = (
    "drive_c/users/steamuser/AppData/Roaming/HellHades Artifact Extractor",
    "drive_c/hh",
)
CREATE_THREAD, VM_OPERATION, VM_WRITE = 0x2, 0x8, 0x20


class Meta:
    """Just enough ECMA-335 metadata parsing to name MethodDef rows."""

    def __init__(self, b):
        self.b = b
        pe = struct.unpack_from("<I", b, 0x3C)[0]
        if b[pe:pe + 4] != b"PE\0\0":
            raise ValueError("not a PE file")
        nsec, optsz = struct.unpack_from("<H", b, pe + 6)[0], struct.unpack_from("<H", b, pe + 20)[0]
        opt = pe + 24
        ddir = opt + (96 if struct.unpack_from("<H", b, opt)[0] == 0x10B else 112)
        clr_rva = struct.unpack_from("<I", b, ddir + 14 * 8)[0]
        self.sections = []
        for i in range(nsec):
            s = opt + optsz + 40 * i
            vsize, va, rawsize, raw = struct.unpack_from("<IIII", b, s + 8)
            self.sections.append((va, max(vsize, rawsize), raw))
        if not clr_rva:
            raise ValueError("not a .NET assembly")
        md = self.off(struct.unpack_from("<I", b, self.off(clr_rva) + 8)[0])
        if struct.unpack_from("<I", b, md)[0] != 0x424A5342:
            raise ValueError("bad metadata signature")
        vlen = struct.unpack_from("<I", b, md + 12)[0]
        p = md + 16 + vlen + 2
        nstreams = struct.unpack_from("<H", b, p)[0]
        p += 2
        streams = {}
        for _ in range(nstreams):
            o, sz = struct.unpack_from("<II", b, p)
            end = b.index(b"\0", p + 8)
            streams[b[p + 8:end].decode()] = (md + o, sz)
            p = p + 8 + ((end - (p + 8)) // 4 + 1) * 4
        self.strings = streams["#Strings"][0]
        tables = streams.get("#~") or streams.get("#-")
        if not tables or "#Strings" not in streams:
            raise ValueError("metadata tables stream missing")
        t = tables[0]
        heap = b[t + 6]
        self.si, gi, bi = (4 if heap & 1 else 2), (4 if heap & 2 else 2), (4 if heap & 4 else 2)
        valid = struct.unpack_from("<Q", b, t + 8)[0]
        rows, p = [0] * 64, t + 24
        for i in range(64):
            if valid >> i & 1:
                rows[i] = struct.unpack_from("<I", b, p)[0]
                p += 4
        if heap & 0x20:  # extra data (uncompressed #- streams)
            p += 4

        def idx(tbl):
            return 4 if rows[tbl] > 0xFFFF else 2

        def coded(tbls, bits):
            return 4 if max(rows[x] for x in tbls) >= 1 << (16 - bits) else 2

        si = self.si
        sizes = [
            2 + si + 3 * gi,                                  # 0 Module
            coded([0, 0x1A, 0x23, 1], 2) + 2 * si,            # 1 TypeRef
            4 + 2 * si + coded([2, 1, 0x1B], 2) + idx(4) + idx(6),  # 2 TypeDef
            idx(4),                                           # 3 FieldPtr
            2 + si + bi,                                      # 4 Field
            idx(6),                                           # 5 MethodPtr
        ]
        for tbl, sz in enumerate(sizes):
            p += rows[tbl] * sz
        self.mdef, self.mdef_rows = p, rows[6]
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
        r = self.mdef + (row - 1) * self.mdef_size
        flags = struct.unpack_from("<H", self.b, r + 6)[0]
        name = struct.unpack_from("<I" if self.si == 4 else "<H", self.b, r + 8)[0]
        s = self.strings + name
        return self.b[s:self.b.index(b"\0", s)].decode("utf-8", "replace"), flags


def find_sites(b, meta):
    """Yield (offset, width, value) of the access constant of each OpenProcess call."""
    for m in re.finditer(rb"\x28(...)\x06", b, re.S):  # call <MethodDef token>
        row = int.from_bytes(m.group(1), "little")
        name, flags = meta.method(row)
        if name != "OpenProcess" or not flags & 0x2000:  # must be the P/Invoke
            continue
        call = m.start()
        # IL pushes (access, inherit, pid): look back for "ldc access; ldc.i4.0/1"
        best = None
        for o in range(call - 1, max(call - 48, 0), -1):
            if b[o] == 0x1F and b[o + 2] in (0x16, 0x17):        # ldc.i4.s imm8
                best = (o + 1, 1, b[o + 1])
            elif b[o] == 0x20 and b[o + 5] in (0x16, 0x17):      # ldc.i4 imm32
                best = (o + 1, 4, struct.unpack_from("<i", b, o + 1)[0])
            if best:
                break
        yield call, best


def notify(msg):
    print(msg, file=sys.stderr)
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        subprocess.run(["notify-send", "-a", "HellHades patch", "HellHades patch", msg],
                       stderr=subprocess.DEVNULL, check=False)


def dll_in_prefix(prefix_id):
    """The Reader DLL in the prefix's HellHades install, and every place looked."""
    pfx = os.path.join(COMPATDATA, prefix_id, "pfx")
    tried = [os.path.join(pfx, install, DLL) for install in INSTALLS]
    return next((p for p in tried if os.path.isfile(p)), None), tried


def main():
    args = [a for a in sys.argv[1:] if a != "-q"]
    quiet = "-q" in sys.argv[1:]
    if len(args) != 1:
        print(__doc__.split("\n\n")[3], file=sys.stderr)
        return 2
    if args[0].isdigit():
        path, tried = dll_in_prefix(args[0])
        if path is None:
            notify(f"no HellHades in prefix {args[0]}; looked at: " + "; ".join(tried))
            return 2
    else:
        path = args[0]
    try:
        b = bytearray(open(path, "rb").read())
        meta = Meta(bytes(b))
    except (OSError, ValueError, KeyError, IndexError, struct.error) as e:
        notify(f"cannot read {path}: {e}")
        return 2
    sites = list(find_sites(bytes(b), meta))
    if not sites:
        notify("no OpenProcess call found in HellHades; layout changed, sell/equip may fail")
        return 1
    changed, problems = [], []
    for call, site in sites:
        if site is None:
            problems.append(f"call at {call:#x}: access constant not found")
            continue
        o, width, val = site
        if val & CREATE_THREAD or (val & (VM_OPERATION | VM_WRITE)) != VM_OPERATION | VM_WRITE:
            continue  # already fine, or a read-only handle that never injects
        new = val | CREATE_THREAD
        if width == 1:
            b[o] = new
        else:
            struct.pack_into("<i", b, o, new)
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
    with open(tmp, "wb") as f:
        f.write(b)
    shutil.copystat(path, tmp)
    os.replace(tmp, path)
    print("patched OpenProcess access at " + ", ".join(changed))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
