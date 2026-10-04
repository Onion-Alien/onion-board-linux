"""Linux side of soundboard.otherboards: where the other soundboards keep their
boards here, and their Windows paths.

- Soundux is a Linux app too: ~/.config/Soundux/config.json (its Flatpak's own
  config folder for the Flatpak), and there its hotkeys are X key codes, not
  Windows ones (linux/soundux.py).
- EXP Soundboard is Java: the board it last had open is in Java's preferences file
  instead of the registry (linux/expboard.py).
- Soundpad and Resanance only run under Wine or Proton: their boards are looked for
  in those prefixes' AppData.

A board made on Windows or under Wine names its files Windows' way. Each Entry
fixes its own path: backslashes become slashes, Z: is / and another drive letter
is that drive in the Wine prefix the board was read from ($WINEPREFIX or ~/.wine
for a board from elsewhere). A file that's there as written is left alone.
"""
from __future__ import annotations

import contextvars
import dataclasses
import os
import re
import sys
from pathlib import Path, PureWindowsPath

from soundboard.linux.wine import DRIVE, in_wine, local_path, prefix_of

__all__ = ["Entry", "sources"]

# the Wine prefix of the board being read (sources()' read sets it)
_prefix: contextvars.ContextVar[Path | None] = contextvars.ContextVar("prefix", default=None)
# a Soundux config written by Soundux for Linux: its hotkeys are X key codes
x_keycodes: contextvars.ContextVar[bool] = contextvars.ContextVar("x_keycodes", default=False)


def _w():
    return sys.modules["soundboard.otherboards"]


@dataclasses.dataclass
class Entry(_w().Entry):
    def __post_init__(self):
        if self.exists or "\\" not in self.path and not DRIVE.match(self.path):
            return
        if self.name == Path(self.path).stem.strip()[:40]:   # the file's name, not a title
            self.name = PureWindowsPath(self.path).stem.strip()[:40] or self.name
        p = local_path(self.path, _prefix.get())
        if Path(p).is_file():
            self.path, self.exists = p, True


def newest(paths: list[Path]) -> Path | None:
    def mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0
    return max(paths, key=mtime, default=None)


def soundux_configs() -> list[Path]:
    """Soundux for Linux's config: its own and its Flatpak's."""
    conf = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    flatpak = Path.home() / ".var" / "app" / "io.github.Soundux" / "config"
    return [p for p in (conf / "Soundux" / "config.json",
                        flatpak / "Soundux" / "config.json") if p.is_file()]


# where each one's board is on Linux, after where its reader looks itself
_ELSEWHERE = {
    "soundpad": lambda: in_wine("Leppsoft/soundlist.spl"),
    "resanance": lambda: in_wine("Resanance/data/Resanance.db"),
    "soundux": lambda: soundux_configs() + in_wine("Soundux/config.json"),
}

_WINDOWS_PATH = re.compile(rb'"[A-Za-z]:\\\\')


def _made_on_linux(path: Path) -> bool:
    """A Soundux config whose sound paths are Linux ones (Soundux for Linux wrote it)."""
    if prefix_of(path):
        return False
    try:
        with open(path, "rb") as f:
            return not _WINDOWS_PATH.search(f.read(1 << 20))
    except OSError:
        return False


def _adapt(src):
    def find():
        if (p := src.find()) is not None:
            return p
        more = _ELSEWHERE.get(src.key)
        return newest(more()) if more else None

    def read(path):
        path = Path(path)
        t1 = _prefix.set(prefix_of(path))
        t2 = x_keycodes.set(src.key == "soundux" and _made_on_linux(path))
        try:
            return src.read(path)
        finally:
            x_keycodes.reset(t2)
            _prefix.reset(t1)

    return dataclasses.replace(src, find=find, read=read)


_upstream_sources = _w().sources


def sources():
    return [_adapt(s) for s in _upstream_sources()]
