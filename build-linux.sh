#!/usr/bin/env bash
# Builds a self-contained Onion Board for Linux (the Linux counterpart of build.ps1):
#   dist/OnionBoard/OnionBoard           (one folder)
#   dist/OnionBoard-x86_64.AppImage      (the one file to give people)
#
# Needs: a Python 3.12+ venv with requirements-dev.txt (.venv), and for the AppImage
# appimagetool on PATH (or APPIMAGETOOL=/path/to/it). Build on the oldest distro you
# want to support (CI uses Ubuntu 22.04): the result needs that glibc or newer.
#
#   ./build-linux.sh             app folder + AppImage
#   ./build-linux.sh --no-appimage
#   ./build-linux.sh --clean     start PyInstaller from scratch
set -euo pipefail
cd "$(dirname "$0")"
py="${PYTHON:-.venv/bin/python}"
[ -x "$py" ] || { echo "No .venv: python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt" >&2; exit 1; }
clean=(); appimage=1
for a in "$@"; do
  case "$a" in
    --clean) clean=(--clean) ;;
    --no-appimage) appimage=0 ;;
    *) echo "unknown option $a" >&2; exit 2 ;;
  esac
done

# the same as build.ps1, with ":" between source and destination; no VB-Cable
# installer (the app makes its own cable on Linux)
mkdir -p build
"$py" -m PyInstaller --noconfirm "${clean[@]}" --windowed \
    --name OnionBoard \
    --add-data "assets/onionboard.ico:." \
    --add-data "assets/art:art" \
    --add-data "assets/radio:radio" \
    --copy-metadata yt-dlp --collect-all yt_dlp_ejs \
    --hidden-import scipy.fft \
    --exclude-module scipy.signal --exclude-module scipy.ndimage \
    --exclude-module scipy.stats --exclude-module scipy.optimize \
    --exclude-module scipy.interpolate --exclude-module scipy.integrate \
    --exclude-module scipy.sparse --exclude-module scipy.spatial \
    --paths . \
    main.py 2>&1 | tee build/pyinstaller.log

# a library PyInstaller couldn't find isn't in the build: the app would start only
# where the user happens to have it (the X11 plugin's libxcb-*, libpulse…)
if grep "Library not found" build/pyinstaller.log; then
  echo "Install the libraries above on this machine so they're bundled, then build again." >&2
  exit 1
fi

# PySide6 brings all of Qt: cut what the app never loads (QML, Quick 3D, translations…)
"$py" scripts/prune_build_linux.py dist/OnionBoard

QT_QPA_PLATFORM=offscreen QTWEBENGINE_DISABLE_SANDBOX="${QTWEBENGINE_DISABLE_SANDBOX:-0}" \
    dist/OnionBoard/OnionBoard --selftest

[ "$appimage" = 1 ] || exit 0
tool="${APPIMAGETOOL:-$(command -v appimagetool || true)}"
[ -n "$tool" ] || { echo "appimagetool not found: set APPIMAGETOOL or use --no-appimage" >&2; exit 1; }
"$py" scripts/make_appdir.py dist/OnionBoard dist/OnionBoard.AppDir
ARCH=x86_64 "$tool" --no-appstream dist/OnionBoard.AppDir dist/OnionBoard-x86_64.AppImage
echo "built dist/OnionBoard-x86_64.AppImage"
