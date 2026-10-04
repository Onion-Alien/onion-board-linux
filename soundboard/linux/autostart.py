"""Linux side of soundboard.autostart: start at login with an XDG autostart entry,
~/.config/autostart/onionboard.desktop (no root; desktops honour Hidden=true as
"switched off", like Task Manager's switch on Windows)."""
from __future__ import annotations

import logging
import os
import shlex
import sys
from pathlib import Path

from soundboard.linux import config_home

log = logging.getLogger(__name__)

__all__ = ["available", "command", "current", "is_enabled", "set_enabled", "refresh",
           "entry_path"]

TRAY_ARG = "--tray"


def entry_path() -> Path:
    return Path(config_home()) / "autostart" / "onionboard.desktop"


def available() -> bool:
    return True


def command(hidden: bool) -> str:
    """The command run at login: the AppImage, the frozen binary, or python main.py."""
    if os.environ.get("APPIMAGE"):
        parts = [os.environ["APPIMAGE"]]
    elif getattr(sys, "frozen", False):
        parts = [sys.executable]
    else:
        main = Path(__file__).resolve().parent.parent.parent / "main.py"
        parts = [sys.executable, str(main)]
    if hidden:
        parts.append(TRAY_ARG)
    return shlex.join(parts)


def _read() -> dict[str, str]:
    try:
        text = entry_path().read_text(encoding="utf-8")
    except OSError:
        return {}
    out = {}
    for line in text.splitlines():
        k, sep, v = line.partition("=")
        if sep and k.strip() and k.strip() not in out:
            out[k.strip()] = v.strip()
    return out


def current() -> str | None:
    return _read().get("Exec")


def is_enabled() -> bool:
    e = _read()
    return "Exec" in e and e.get("Hidden", "false").lower() != "true" \
        and e.get("X-GNOME-Autostart-enabled", "true").lower() != "false"


def set_enabled(on: bool, hidden: bool = True) -> bool:
    p = entry_path()
    try:
        if on:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text("[Desktop Entry]\nType=Application\nName=Onion Board\n"
                           f"Exec={command(hidden)}\nIcon=onionboard\nTerminal=false\n"
                           "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")
            tmp.replace(p)
        else:
            p.unlink(missing_ok=True)
        return True
    except OSError:
        log.warning("couldn't change start at login", exc_info=True)
        return False


def refresh(hidden: bool):
    cur = current()
    if cur is not None and cur != command(hidden) and is_enabled():
        set_enabled(True, hidden)
