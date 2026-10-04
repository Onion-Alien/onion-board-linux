"""Linux side of soundboard.soundux: Soundux for Linux saves its hotkeys as X key
codes (what its X input listener saw), not Windows virtual-key codes. A config it
wrote (linux/otherboards.py tells: its sound paths are Linux ones) has them turned
into Windows codes first; one copied over from Windows is read as it is."""
from __future__ import annotations

import sys

from soundboard.linux import x11
from soundboard.linux.otherboards import x_keycodes

__all__ = ["hotkey"]

_upstream_hotkey = sys.modules["soundboard.soundux"].hotkey   # this runs at its end


def _vk(code) -> int:
    """An X key code -> its Windows code (a US layout, by the key's place); 0 for none
    (codes below 8 are mouse buttons)."""
    if not isinstance(code, int) or isinstance(code, bool) or code < 8:
        return 0
    return x11.EVDEV_TO_VK.get(code - 8, 0)


def hotkey(keys) -> str:
    if not x_keycodes.get() or not isinstance(keys, list):
        return _upstream_hotkey(keys)
    vks = []
    for k in keys:
        if isinstance(k, dict):
            if k.get("type", 0) not in (0, "keyboard"):
                return ""
            k = k.get("key")
        if not (vk := _vk(k)):
            return ""
        vks.append(vk)
    return _upstream_hotkey(vks)
