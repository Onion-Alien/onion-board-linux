"""Windows wording → Linux wording, in one place.

The app's text is written for Windows ("Windows' default output", "the Windows
Recycle Bin", "%APPDATA%\\OnionBoard"…) inline all over the upstream modules.
Instead of editing those, install() wraps the Qt calls that put text on screen
(labels, buttons, tooltips, message boxes, combo items, tabs, the tray, the
clipboard) so each string goes through linux() on its way in.

PHRASES are matched anywhere in a text, case-sensitive, also in their
HTML-escaped form (a toast escapes its message). WHOLE are exact whole texts,
for short ones like "Windows default" that mustn't match inside other text.
tests/test_linux_wording.py checks every "Windows" string in the app's source is
either reworded here or never shown on Linux (a Windows-only feature or code path).
"""
from __future__ import annotations

import html
import os
import re
import sys
from pathlib import Path

from soundboard.linux import data_home


def _data_dir() -> str:
    """The data folder as people would type it: ~/.local/share/OnionBoard."""
    p = Path(data_home()) / "OnionBoard"
    try:
        return "~/" + str(p.relative_to(Path.home()))
    except ValueError:
        return str(p)


PHRASES: list[tuple[str, str]] = [
    # the data folder (APPDATA is the XDG data folder on Linux: soundboard/linux)
    ("%APPDATA%\\OnionBoard", _data_dir()),
    # already running (singleinstance.py)
    ("look for its icon in the taskbar tray (the ^ arrow by the clock)",
     "look for its icon in the system tray"),
    ("end “Onion Board” in Task Manager and start it again",
     "end “OnionBoard” in your system monitor and start it again"),
    # devices (mainwindow.py): the cable is made by the app, no restart
    ("Still no virtual cable. If you just installed it, restart your PC — Windows often "
     "only shows it after a restart.",
     "Still no virtual cable: press “Make the virtual cable”."),
    ("Windows' default output", "the system's default output"),
    # a Bluetooth headset's mic (linux/ui.py: told by its sound server name)
    ("while it's open, Windows switches the headset to call quality",
     "while it's open, the headset switches to call quality"),
    # Settings
    ("Couldn't change Windows startup", "Couldn't change starting at sign-in"),
    ("Translation models (Voice tab), live voice's speech model (Hugging Face) and "
     "Windows' own voices (Windows Update).",
     "Translation models (Voice tab) and live voice's speech model (Hugging Face)."),
    # files
    ("re-zip it with Windows (Send to → Compressed folder)",
     "re-zip it with your file manager (Compress)"),
    ("the Windows Recycle Bin", "the Trash"),
    # the Voice tab's Reload voices (Windows' voice installs are hidden: linux/ui.py)
    ("pick up new Windows voices", "pick up new voices"),
    # errors.py
    ("Windows' audio system refused", "The sound server refused"),
    ("Windows denied access", "Access was denied"),
    ("Windows reported a problem.", "The system reported a problem."),
    # Settings → Remote's prompt for an AI helper (copied to the clipboard)
    ("a free Windows soundboard", "a free soundboard"),
    # custom voices (Piper's Linux release: linux/customvoices.py) and Tor's errors
    ("but no piper.exe (put it in a 'piper' folder there)",
     "but no piper program (put the “piper” folder from Piper's Linux download there)"),
    ("tor.exe", "tor"),
    # the cable's ends are the app's own (linux/vcable.py), not VB-Cable's: the guides'
    # name for the mic to pick before the cable is made, and Settings' OBS tip
    ("CABLE Output", "Onion Board Cable Output"),
    ("CABLE Input", "Onion Board Cable Input"),
    ("A second virtual cable (free: VB-Cable A+B from vb-audio.com) is ideal; then use "
     "Audio Input Capture → its Output end.",
     "A device of its own is ideal: pactl load-module module-null-sink sink_name=obs "
     "makes one (until you log out)."),
    ("a free add-on that works like an invisible microphone.",
     "an invisible microphone the app makes for you."),
    ("install the free virtual cable.", "make the virtual cable (one click, nothing to "
     "download)."),
    # the tray isn't "by the clock" on every desktop
    ("The tray icon (by the clock) opens it again", "The tray icon opens it again"),
    ("right-click its icon by the clock → Exit", "right-click its tray icon → Exit Steam"),
    # self-update: the AppImage replaces itself (linux/updates.py)
    ("Update now downloads it in the background (about 180 MB)",
     "Update now downloads it in the background (about 210 MB)"),
    ("The installer couldn't be started", "The update couldn't be put in place"),
    # add-ons (linux/modules.py): the distribution's python3, the install.sh fallback
    ("Python isn't installed. Get it from python.org (tick \"Add python.exe to PATH\"), "
     "then press Install again.",
     "Python 3.12 or newer isn't installed. Install it with your distribution's package "
     "manager (with venv: python3-venv on Debian and Ubuntu), then press Install again."),
    ("install.bat", "install.sh"),
    ("Needs Python 3.12+ from python.org.",
     "Needs Python 3.12 or newer: your distribution's python3, with venv."),
    # hotkeys (settings.pretty_key): the Windows key is Super on Linux
    ("Windows+", "Super+"),
]



def update_phrases(frozen: bool, appimage: str) -> list[tuple[str, str]]:
    """A built copy that can't update itself isn't "running from source": say why.
    linux/updates.py updates only an AppImage whose folder the user can write to."""
    if not frozen:
        return []   # really from source: git pull is right
    if not appimage:
        why = ("This copy isn't the AppImage, so it can't update itself: get the new "
               "version from the release page")
    else:
        why = (f"This AppImage is in a folder you can't write to "
               f"({os.path.dirname(appimage)}), so it can't replace itself: move it to "
               "one you can (your home folder, say), or get the new one from the release page")
    return [("This copy runs from source, so it only tells you: update it with git pull.",
             f"{why}. It only tells you when one is out."),
            ("This copy runs from source: update it with <code>git pull</code>.",
             html.escape(why) + ".")]


PHRASES += update_phrases(bool(getattr(sys, "frozen", False)), os.environ.get("APPIMAGE", ""))

WHOLE: dict[str, str] = {
    "Windows default": "Default voice",   # the Voice tab's voice list
    "I've installed it — check again": "Check again",   # the Setup tab: nothing to install
    "Windows": "Super", "Left Windows": "Left Super", "Right Windows": "Right Super",
}


def _table() -> dict[str, str]:
    t = {}
    for old, new in PHRASES:
        t[old] = new
        t.setdefault(html.escape(old), html.escape(new))
        t.setdefault(html.escape(old, quote=False), html.escape(new, quote=False))
    return t


_MAP = _table()
_RE = re.compile("|".join(re.escape(k) for k in sorted(_MAP, key=len, reverse=True)))


active = True   # tests of upstream's own text switch it off (tests/platform_hooks.py)


def linux(text):
    """`text` in Linux wording; anything that isn't a str comes back as it is."""
    if type(text) is not str or not active:
        return text
    whole = WHOLE.get(text)
    if whole is not None:
        return whole
    return _RE.sub(lambda m: _MAP[m.group(0)], text) if _RE.search(text) else text


# ---------------------------------------------------------------- the Qt calls

FIRST = "first"   # the first str argument is the text: (text, data) or (icon, text, data)


def _wrap(cls, name: str, args=(0,), kwargs: tuple[str, ...] = ()):
    """Make cls.name pass its text arguments through linux(): positional `args`
    (indexes after self, or FIRST) and keyword `kwargs`."""
    orig = getattr(cls, name, None)
    if orig is None or getattr(orig, "_linux_wording", False):
        return

    def wrapper(self, *a, **k):
        if a:
            if args == FIRST:
                i = next((i for i, v in enumerate(a) if type(v) is str), None)
                if i is not None:
                    a = (*a[:i], linux(a[i]), *a[i + 1:])
            else:
                a = tuple(linux(v) if i in args else v for i, v in enumerate(a))
        for key in kwargs:
            if key in k:
                k[key] = linux(k[key])
        return orig(self, *a, **k)

    wrapper._linux_wording = True
    wrapper.__name__ = name
    setattr(cls, name, wrapper)


def _wrap_static(cls, name: str, args: tuple[int, ...]):
    """The same for a static method (QMessageBox.information(parent, title, text…))."""
    func = getattr(cls, name, None)
    if func is None or getattr(func, "_linux_wording", False):
        return

    def wrapper(*a, **k):
        a = tuple(linux(v) if i in args else v for i, v in enumerate(a))
        for key in ("title", "text"):
            if key in k:
                k[key] = linux(k[key])
        return func(*a, **k)

    wrapper._linux_wording = True
    setattr(cls, name, staticmethod(wrapper))


_installed = False


def install() -> None:
    """Wrap Qt's text calls (once). Text set from C++ (Qt's own dialogs) is untouched."""
    global _installed
    if _installed:
        return
    _installed = True
    from PySide6.QtGui import QAction, QClipboard
    from PySide6.QtWidgets import (QAbstractButton, QCheckBox, QComboBox, QGroupBox, QLabel,
                                   QLineEdit, QMenu, QMessageBox, QPushButton, QRadioButton,
                                   QSystemTrayIcon, QTabWidget, QWidget)
    # constructors whose first argument can be the text: QLabel("…"), QPushButton("…")
    for cls in (QLabel, QPushButton, QCheckBox, QRadioButton, QGroupBox):
        _wrap(cls, "__init__", (0,), ("text", "title"))
    _wrap(QAction, "__init__", FIRST)   # (text, parent) or (icon, text, parent)
    for cls, name in ((QLabel, "setText"), (QAbstractButton, "setText"),
                      (QAction, "setText"), (QAction, "setToolTip"),
                      (QWidget, "setToolTip"), (QWidget, "setWindowTitle"),
                      (QGroupBox, "setTitle"), (QLineEdit, "setPlaceholderText"),
                      (QMessageBox, "setText"), (QMessageBox, "setInformativeText"),
                      (QClipboard, "setText"), (QMenu, "setTitle")):
        _wrap(cls, name)
    _wrap(QMenu, "addAction", FIRST)       # (text, …) or (icon, text, …)
    _wrap(QComboBox, "addItem", FIRST)     # (text, data) or (icon, text, data)
    _wrap(QComboBox, "insertItem", FIRST)  # (index, text, data) or (index, icon, text…)
    _wrap(QComboBox, "setItemText", (1,))
    _wrap(QTabWidget, "addTab", FIRST)     # (widget, text) or (widget, icon, text)
    _wrap(QTabWidget, "insertTab", FIRST)
    _wrap(QTabWidget, "setTabText", (1,))
    _wrap(QTabWidget, "setTabToolTip", (1,))
    _wrap(QMessageBox, "__init__", (1, 2))   # (icon, title, text, …)
    _wrap(QSystemTrayIcon, "showMessage", (0, 1))
    _wrap(QSystemTrayIcon, "setToolTip")
    for name in ("information", "warning", "question", "critical"):
        _wrap_static(QMessageBox, name, (1, 2))   # (parent, title, text, …)


__all__: list[str] = []
