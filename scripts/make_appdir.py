"""Turn the PyInstaller folder (dist/OnionBoard) into an AppImage's AppDir for
appimagetool (build-linux.sh runs this):

    OnionBoard.AppDir/
      AppRun                 starts usr/lib/onionboard/OnionBoard with the arguments
      onionboard.desktop     the menu entry appimagetool requires
      onionboard.png         the icon, drawn by the app's own theme.app_icon()
      usr/lib/onionboard/    the app folder

Usage: python scripts/make_appdir.py dist/OnionBoard dist/OnionBoard.AppDir
"""
from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

APPRUN = """#!/bin/sh
# Onion Board's AppImage entry: the app lives in usr/lib/onionboard
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/onionboard/OnionBoard" "$@"
"""

DESKTOP = """[Desktop Entry]
Type=Application
Name=Onion Board
GenericName=Soundboard
Comment=Play sounds into Discord and games through your mic
Exec=OnionBoard %F
Icon=onionboard
Terminal=false
Categories=AudioVideo;Audio;
Keywords=soundboard;discord;voice changer;mic;
StartupWMClass=OnionBoard
"""


def icon_png(path: Path, size: int = 256):
    """The app icon as a PNG, painted by the app (no image files in the repo)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT))
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])   # noqa: F841 - painting needs one
    from soundboard import theme
    if not theme.logo_image(size).save(str(path), "PNG"):
        raise SystemExit(f"couldn't write {path}")


def make(app: Path, appdir: Path):
    if not (app / "OnionBoard").is_file():
        raise SystemExit(f"{app}/OnionBoard not found: run PyInstaller first")
    if appdir.exists():
        shutil.rmtree(appdir)
    lib = appdir / "usr" / "lib" / "onionboard"
    shutil.copytree(app, lib, symlinks=True)
    run = appdir / "AppRun"
    run.write_text(APPRUN, encoding="utf-8")
    run.chmod(run.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (appdir / "onionboard.desktop").write_text(DESKTOP, encoding="utf-8")
    icon_png(appdir / "onionboard.png")
    (appdir / ".DirIcon").symlink_to("onionboard.png")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    make(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"made {sys.argv[2]}")
