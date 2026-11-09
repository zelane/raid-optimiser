"""Add a CA certificate to a Wine prefix's user root store (HKCU, user.reg).

Proton under umu runs in the Steam Linux Runtime, whose Wine syncs its machine root store
(HKLM) from the runtime's certificates, not the host's: trusting mitmproxy's CA on the host
doesn't reach Windows apps there. The user store isn't synced, so a certificate added there
stays. The value is crypt32's serialized form: (property id, 1, length, data) elements,
here the SHA-1 hash (3) and the DER certificate (32).

    python3 -I tools/wine_trust_ca.py <prefix> ~/.mitmproxy/mitmproxy-ca-cert.pem

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


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    prefix, pem = Path(sys.argv[1]), Path(sys.argv[2])
    user_reg = prefix / "user.reg"
    if not user_reg.is_file():
        sys.exit(f"no user.reg in {prefix}")
    running = subprocess.run(["pgrep", "-x", "wineserver"], capture_output=True).returncode == 0
    if running:
        sys.exit("wineserver is running: close the game and the extractor first")
    cert = der(pem.read_text())
    sha1 = hashlib.sha1(cert).digest()
    thumb = sha1.hex().upper()
    text = user_reg.read_text(encoding="utf-8", errors="surrogateescape")
    if f"[{KEY}\\\\{thumb}]" in text:
        print(f"already in {user_reg} ({thumb})")
        return
    blob = element(3, sha1) + element(32, cert)
    block = f"\n[{KEY}\\\\{thumb}] {int(time.time())}\n{reg_hex(blob)}\n"
    with user_reg.open("a", encoding="utf-8", errors="surrogateescape") as f:
        f.write(block)
    print(f"added {pem.name} ({thumb}) to {user_reg}")


if __name__ == "__main__":
    main()
