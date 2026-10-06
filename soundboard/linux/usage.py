"""Linux side of soundboard.usage: the same anonymous count, told apart from Windows.

The daily "still here" goes to /app/linux/<version> (titled "Onion Board <version>
(Linux)") instead of /app/<version>, and each event gets /linux on the end
(first-start/linux, update-now/<from>-to-<to>/linux). Nothing else changes: the same
switch (Settings > Privacy & security > Usage count), the same random ID, nothing
more sent. There's no installer on Linux, so no "Count me in" box: it's on unless
switched off there, like a new Windows install with the box left ticked."""
from __future__ import annotations

from soundboard import usage as _usage

__all__ = ["hits"]

active = True                 # off: upstream's paths (tests/platform_hooks.py)
_windows_hits = _usage.hits   # upstream's, before this module replaces it


def hits(cfg, now: float, event: str = "") -> list[dict]:
    out = _windows_hits(cfg, now, event)
    if not active:
        return out
    for h in out:
        if h.get("event"):
            h["path"] = h["title"] = h["path"].rstrip("/") + "/linux"
        elif h["path"].startswith("/app/"):
            h["path"] = "/app/linux/" + h["path"][len("/app/"):]
            h["title"] += " (Linux)"
    return out
