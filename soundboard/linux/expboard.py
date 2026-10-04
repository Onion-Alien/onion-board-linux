"""Linux side of soundboard.expboard: EXP Soundboard (Java) remembers the board it
last had open in Java's preferences file, ~/.java/.userPrefs/<node>/prefs.xml, as a
plain value (the registry's escaping is Windows' only)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

__all__ = ["_last_board"]

NODE = "Expenosa's Soundboard"
KEY = "lastSoundboardUsed"


def _last_board() -> Path | None:
    prefs = Path.home() / ".java" / ".userPrefs" / NODE / "prefs.xml"
    try:
        if prefs.stat().st_size > 1 << 20:
            return None
        root = ET.fromstring(prefs.read_bytes())
    except (OSError, ET.ParseError):
        return None
    for e in root.iter("entry"):
        if e.get("key") == KEY and (v := e.get("value")):
            p = Path(v)
            return p if p.is_file() else None
    return None
