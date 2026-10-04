"""Wine and Proton from the Linux side: where their prefixes are, and which Linux
file a Windows path in one of them means.

A prefix is a folder holding drive_c (C:) and dosdevices (a link per drive letter);
Z: is the Linux file system's root in every prefix. Steam keeps a Proton prefix per
game in steamapps/compatdata/<app id>/pfx.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# a drive letter, the last one in the path: a reader that joined a folder and an absolute
# Windows path made "C:\\Music/D:\\x.mp3" (Windows names can't hold a ':')
DRIVE = re.compile(r"(?:.*[\\/])?([A-Za-z]):(?:[\\/](.*))?$", re.S)


def default_prefix() -> Path:
    return Path(os.environ.get("WINEPREFIX") or Path.home() / ".wine")


def prefix_of(path: Path) -> Path | None:
    """The Wine prefix a file is in (the folder holding drive_c), if it's in one."""
    for d in Path(path).parents:
        if d.name == "drive_c":
            return d.parent
    return None


def local_path(win: str, prefix: Path | None = None) -> str:
    """A Windows path from a board -> where that file is here."""
    if m := DRIVE.match(win):
        rest = (m.group(2) or "").replace("\\", "/")
        letter = m.group(1).lower()
        if letter == "z":
            return "/" + rest
        prefix = prefix or default_prefix()
        root = prefix / "dosdevices" / f"{letter}:"
        if not root.exists() and letter == "c":
            root = prefix / "drive_c"
        return str(root / rest)
    return win.replace("\\", "/")


def _steam_roots() -> list[Path]:
    home = Path.home()
    return [home / ".steam" / "steam", home / ".local" / "share" / "Steam",
            home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam"]


def prefixes() -> list[Path]:
    """Wine prefixes on this computer: $WINEPREFIX, ~/.wine and Steam's Proton ones."""
    out = [default_prefix(), Path.home() / ".wine"]
    for s in _steam_roots():
        try:
            out += sorted(s.glob("steamapps/compatdata/*/pfx"))
        except OSError:
            pass
    seen, uniq = set(), []
    for p in out:
        try:
            key = p.resolve()
        except OSError:
            continue
        if key not in seen and (p / "drive_c").is_dir():
            seen.add(key)
            uniq.append(p)
    return uniq


def in_wine(rel: str) -> list[Path]:
    """`rel` (e.g. "Leppsoft/soundlist.spl") in each Wine user's AppData\\Roaming."""
    out = []
    for pfx in prefixes():
        for roaming in ("AppData/Roaming", "Application Data"):
            try:
                out += [p for p in (pfx / "drive_c" / "users").glob(f"*/{roaming}/{rel}")
                        if p.is_file()]
            except OSError:
                pass
    return out
