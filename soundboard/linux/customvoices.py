"""Linux side of soundboard.speech.customvoices: Piper's Linux release, and the
voices folder's README in Linux terms.

Piper's Linux download (piper_linux_x86_64.tar.gz) unpacks to a `piper` folder
holding the `piper` program next to its libraries; Windows' has piper.exe."""
from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

__all__ = ["README", "_piper_exe"]


def _piper_exe(d: Path) -> str:
    """The piper program for the voice packs in `d`: in a `piper` folder there (as
    Piper's release unpacks), loose in `d`, or on PATH; "" if there's none."""
    for p in (d / "piper" / "piper", d / "piper.bin"):
        if p.is_file():
            if not os.access(p, os.X_OK):   # copied from a file manager / an archive tool
                try:
                    p.chmod(p.stat().st_mode | stat.S_IXUSR)
                except OSError:
                    continue
            return str(p)
    return shutil.which("piper") or ""


def _readme() -> str:
    from soundboard.speech import customvoices   # this runs at the end of its import
    text = customvoices.README
    for old, new in (
            ('"C:/tools/tts.exe"', '"/usr/local/bin/mytts"'),
            ("and piper.exe\n   (from github.com/rhasspy/piper releases) into a \"piper\" "
             "folder here.",
             "and the \"piper\"\n   folder from Piper's Linux download "
             "(github.com/rhasspy/piper releases,\n   piper_linux_x86_64.tar.gz) here, or "
             "install piper so it's on PATH."),
            ("A TTS server running on your PC", "A TTS server running on this computer")):
        text = text.replace(old, new)
    return text


README = _readme()
