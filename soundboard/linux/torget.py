"""Linux side of soundboard.torget: the Tor Expert Bundle for Linux. Same release
and the same checks; the SHA-256 is from that release's sha256sums-signed-build.txt.
The binaries come out of the tarball without their execute bit (unpack writes the
bytes), so it is put back."""
from __future__ import annotations

import stat
from pathlib import Path

__all__ = ["TARBALL", "URL", "SHA256", "KEEP", "unpack"]


def _g():
    from soundboard import torget
    return torget


_orig_unpack = _g().unpack
VERSION = _g().VERSION
TARBALL = f"tor-expert-bundle-linux-x86_64-{VERSION}.tar.gz"
URL = f"https://dist.torproject.org/torbrowser/{VERSION}/{TARBALL}"
SHA256 = "8e012ec6815d7899cb64011582e2dade88e74119c6661068a2a3252de0ccd7f2"
KEEP = {
    "tor/tor": "tor",
    "tor/libcrypto.so.3": "libcrypto.so.3",
    "tor/libssl.so.3": "libssl.so.3",
    "tor/libevent-2.1.so.7": "libevent-2.1.so.7",
    "tor/pluggable_transports/lyrebird": "pluggable_transports/lyrebird",
    "tor/pluggable_transports/pt_config.json": "pluggable_transports/pt_config.json",
    "docs/tor.txt": "docs/tor.txt",
    "docs/lyrebird.txt": "docs/lyrebird.txt",
    "docs/libevent.txt": "docs/libevent.txt",
    "docs/openssl.txt": "docs/openssl.txt",
}
EXECUTABLE = ("tor", "pluggable_transports/lyrebird")


def unpack(data: bytes, dest: Path | None = None) -> Path:
    dest = _orig_unpack(data, dest)
    for rel in EXECUTABLE:
        p = dest / rel
        try:
            p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass
    return dest
