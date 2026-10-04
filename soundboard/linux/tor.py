"""Linux side of soundboard.tor: the binary is `tor` (from the downloaded Linux
Expert Bundle, else the system's), it finds its libssl / libevent next to itself
through LD_LIBRARY_PATH (the bundle's tor has no rpath), and the pluggable
transports' path uses "/". Tor still exits with the app through
__OwningControllerProcess and TAKEOWNERSHIP, so no job object is needed."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

__all__ = ["bundle_dir", "tor_exe", "bridge_config"]

EXE = "tor"


def _t():
    from soundboard import tor
    return tor


def bundle_dir() -> Path:
    """The bundle's folder: the first of bundle_dirs() that has `tor`, else the
    download's."""
    t = _t()
    for d in t.bundle_dirs():
        if (d / EXE).is_file():
            return d
    return t.torget.bin_dir()


def tor_exe() -> Path | None:
    p = bundle_dir() / EXE
    if p.is_file():
        return p
    system = shutil.which("tor")   # a distro's tor works too (no bridges without the bundle)
    return Path(system) if system else None


def bridge_config(kind: str, pt: dict) -> list[str]:
    """As tor.bridge_config, with the transport's relative path in Linux form."""
    plugin_key = {"snowflake": "snowflake", "obfs4": "lyrebird"}.get(kind)
    plugin = (pt.get("pluggableTransports") or {}).get(plugin_key or "")
    lines = (pt.get("bridges") or {}).get(kind) or []
    if not plugin or not lines:
        raise ValueError(f"this copy of Tor has no {kind} bridges")
    plugin = plugin.replace("${pt_path}", "pluggable_transports/")
    return ["UseBridges 1", plugin, *(f"Bridge {b}" for b in lines)]


def _command(self, exe: Path) -> list[str]:
    """The bundle's libraries sit beside tor: `env` puts them on its library path
    without touching this process's environment."""
    lib = str(Path(exe).parent)
    old = os.environ.get("LD_LIBRARY_PATH")
    return ["env", f"LD_LIBRARY_PATH={lib}:{old}" if old else f"LD_LIBRARY_PATH={lib}",
            str(exe)]


_t().Tor._command = _command
