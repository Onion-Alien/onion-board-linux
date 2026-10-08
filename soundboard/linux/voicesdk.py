"""Linux side of soundboard.voicesdk: the game in front, on X11 (which covers games
under XWayland, so every Proton game).

The active window (the root window's _NET_ACTIVE_WINDOW) names its process
(_NET_WM_PID). A Windows game under Wine or Proton runs inside Wine's loader, so its
.exe is the first word of its command line, a Windows path: Z:\\ is the Linux file
system, another drive is in the prefix from the process's WINEPREFIX. A native
program is /proc/<pid>/exe. Only what any program may read about another of the same
user's in /proc: never the game's memory.

The scan then finds Vivox, Photon and Dissonance in a Proton game's folder as on
Windows. A native Linux game shows only Unity's managed Photon / Dissonance
libraries (.dll on every system), not a native libvivoxsdk.so. A Wayland window has
no _NET_ACTIVE_WINDOW: nothing is suggested while one is in front.

System programs (the desktop's own panel and shell, anything under /usr, Wine's own
programs in C:\\windows) don't count, as Windows' own windows don't.
"""
from __future__ import annotations

import os
from pathlib import Path

from soundboard.linux import x11
from soundboard.linux.wine import DRIVE, default_prefix, local_path

__all__ = ["_is_system", "foreground_process"]

SYSTEM_DIRS = ("/usr/", "/bin/", "/sbin/", "/lib/", "/lib64/", "/snap/", "/nix/store/",
               "/app/")   # /app: a Flatpak's own files

_dpy: x11.Display | None = None   # the UI thread's own connection, kept open

# Who's listening (Listeners): the voice chat programs' Linux names, beside upstream's
# .exe ones (a Windows one under Wine / Proton is still named by its .exe). Discord's
# own clients and the ones built on it (Vesktop, WebCord, Legcord) are Discord.
_DISCORD, _BROWSER = ("discord", "Discord"), ("webrtc", "Your browser")
LINUX_VOICE_APPS = {
    **dict.fromkeys(("discord", "discordptb", "discordcanary", "vesktop", "webcord",
                     "legcord", "armcord", "equibop"), _DISCORD),
    **dict.fromkeys(("firefox", "firefox-bin", "firefox-esr", "librewolf", "floorp",
                     "waterfox", "zen", "zen-bin", "chrome", "google-chrome", "chromium",
                     "chromium-browser", "brave", "brave-browser", "opera", "vivaldi-bin",
                     "msedge", "microsoft-edge"), _BROWSER),
    "zoom": ("webrtc", "Zoom"),
    "teams-for-linux": ("webrtc", "Microsoft Teams"),
    **dict.fromkeys(("ts3client_linux_amd64", "ts3client_linux_x86", "teamspeak",
                     "teamspeak3", "teamspeak-client"), ("game", "TeamSpeak")),
    "mumble": ("game", "Mumble"),
}
_up = __import__("sys").modules.get("soundboard.voicesdk")   # this runs at its end
if _up is not None:
    # 1.9.4+: VOICE_APPS translates the names each time it's read, from _VOICE_APPS
    raw = getattr(_up, "_VOICE_APPS", None)
    (raw if isinstance(raw, dict) else _up.VOICE_APPS).update(LINUX_VOICE_APPS)


def _display() -> x11.Display | None:
    global _dpy
    if _dpy is not None and not _dpy.alive:
        _dpy = None
    if _dpy is None and x11.available():
        try:
            _dpy = x11.Display()
        except OSError:
            return None
    return _dpy


def active_window() -> int:
    """The window in front (X11: the window manager's _NET_ACTIVE_WINDOW), or 0."""
    d = _display()
    if d is None:
        return 0
    win = d.cardinals(d.root, "_NET_ACTIVE_WINDOW")
    return win[0] if win else 0


def active_pid() -> int:
    """The process of the window in front (X11), or 0."""
    win = active_window()
    if not win:
        return 0
    pid = _display().cardinals(win, "_NET_WM_PID")
    return pid[0] if pid else 0


def active_window_rect() -> tuple[int, int, int, int] | None:
    """Where the window in front is, in native pixels (also the overlay's "the one the
    game is on": linux/keys.py), or None."""
    win = active_window()
    return _display().window_rect(win) if win else None


def _environ(pid: int, name: str) -> str:
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            data = f.read(1 << 20)
    except OSError:
        return ""
    key = name.encode() + b"="
    for item in data.split(b"\0"):
        if item.startswith(key):
            return item[len(key):].decode("utf-8", "replace")
    return ""


def exe_of(pid: int) -> str:
    """The program a process runs: a Wine / Proton process's Windows .exe as a Linux
    path, else /proc/<pid>/exe; "" when it can't be read."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            argv0 = f.read(4096).split(b"\0", 1)[0].decode("utf-8", "replace")
    except OSError:
        return ""
    if argv0.lower().endswith(".exe"):
        if DRIVE.match(argv0):
            prefix = _environ(pid, "WINEPREFIX")
            return local_path(argv0, Path(prefix) if prefix else default_prefix())
        if argv0.startswith("/"):
            return argv0
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return ""


def foreground_process() -> tuple[int, str]:
    """(pid, program path) of the window you're using, or (0, ''). This app's own
    windows count as none."""
    try:
        pid = active_pid()
        if not pid or pid == os.getpid():
            return 0, ""
        path = exe_of(pid)
        return (pid, path) if path else (0, "")
    except Exception:  # noqa: BLE001 - a suggestion must never break the app
        return 0, ""


def _is_system(path: str) -> bool:
    """The desktop's own programs and Wine's: passing through them on the way from a
    game to this app shouldn't count as leaving the game. Strings only (runs on the
    UI thread)."""
    if not path:
        return False
    p = path.replace("\\", "/")
    return p.startswith(SYSTEM_DIRS) or "/drive_c/windows/" in p.lower()
