"""Linux side of soundboard.directmic: "Straight into my mic" isn't here yet.

On Windows it's a capture effect (an APO DLL) put on the real mic with an admin
prompt, read through the registry. None of that exists on Linux, so here the mic is
never "ready": the route stays the virtual cable (linux/library.py drops "mic" from
the routes, linux/ui.py hides its buttons). Every question the app asks gets the
answer "not on any mic", and nothing ever asks for admin or touches a Windows path.
"""
from __future__ import annotations

from pathlib import Path

__all__ = ["AVAILABLE", "anything_installed", "capture_endpoints", "cli", "endpoint_for",
           "install", "installed_on", "registered_dll", "uninstall"]

AVAILABLE = False   # the app may offer the mic route (Windows: True, by its absence)
NOT_HERE = "Straight into my mic isn't on Linux yet: use the virtual cable."


def capture_endpoints() -> list[dict]:
    return []


def endpoint_for(name: str | None) -> str | None:
    return None


def installed_on() -> list[str]:
    return []


def registered_dll() -> Path | None:
    return None


def anything_installed() -> bool:
    return False


def install(mic_name: str | None) -> str | None:
    return NOT_HERE


def uninstall() -> str | None:
    return None


def cli(args: list[str]) -> int:
    """`--direct-mic remove` (an uninstaller's) has nothing to remove; the admin steps
    don't exist here."""
    return 0 if args == ["remove"] else 2
