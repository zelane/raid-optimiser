"""Add a CA certificate to a Wine prefix's user root store (HKCU, user.reg).

Proton under umu runs in the Steam Linux Runtime, whose Wine syncs its machine root store
(HKLM) from the runtime's certificates, not the host's: trusting mitmproxy's CA on the host
doesn't reach Windows apps there. The user store isn't synced, so a certificate added there
stays. The value is crypt32's serialized form: (property id, 1, length, data) elements,
here the SHA-1 hash (3) and the DER certificate (32).

    uv run python -m tools.wine_trust_ca <prefix> ~/.mitmproxy/mitmproxy-ca-cert.pem   # just ca

Run with Wine stopped: wineserver rewrites user.reg when it exits.
"""

import base64
import hashlib
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

import click

KEY = r"Software\\Microsoft\\SystemCertificates\\Root\\Certificates"


def der(pem: str) -> bytes:
    body = re.search(r"-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----", pem, re.S)
    if not body:
        sys.exit("no certificate in the PEM file")
    return base64.b64decode("".join(body.group(1).split()))


def element(prop: int, data: bytes) -> bytes:
    return struct.pack("<III", prop, 1, len(data)) + data


def reg_hex(data: bytes) -> str:
    out, line = [], '"Blob"=hex:'
    for i, b in enumerate(data):
        part = f"{b:02x}" + ("," if i < len(data) - 1 else "")
        if len(line) + len(part) > 78:
            out.append(line + "\\")
            line = "  "
        line += part
    return "\n".join(out + [line])


@click.command(help=__doc__)
@click.argument("prefix", type=click.Path(file_okay=False, path_type=Path))
@click.argument("pem", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def main(prefix: Path, pem: Path) -> None:
    user_reg = prefix / "user.reg"
    if not user_reg.is_file():
        sys.exit(f"no user.reg in {prefix}")
    cert = der(pem.read_text())
    sha1 = hashlib.sha1(cert).digest()
    thumb = sha1.hex().upper()
    text = user_reg.read_text(encoding="utf-8", errors="surrogateescape")
    if f"[{KEY}\\\\{thumb}]" in text:
        print(f"already in {user_reg} ({thumb})")
        return
    # Only writing needs Wine stopped: checking for the certificate is fine while it runs.
    running = subprocess.run(["pgrep", "-x", "wineserver"], capture_output=True).returncode == 0
    if running:
        sys.exit("wineserver is running: close the game and the extractor first")
    blob = element(3, sha1) + element(32, cert)
    block = f"\n[{KEY}\\\\{thumb}] {int(time.time())}\n{reg_hex(blob)}\n"
    with user_reg.open("a", encoding="utf-8", errors="surrogateescape") as f:
        f.write(block)
    print(f"added {pem.name} ({thumb}) to {user_reg}")


if __name__ == "__main__":
    main()
