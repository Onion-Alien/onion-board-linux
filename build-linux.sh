#!/usr/bin/env bash
# Builds a self-contained Onion Board for Linux (the Linux counterpart of build.ps1):
#   dist/OnionBoard/OnionBoard           (one folder)
#   dist/OnionBoard-x86_64.AppImage      (the one file to give people)
#
# Needs: a Python 3.12+ venv with requirements-dev.txt and requirements-linux.txt
# (.venv), git + a C compiler + the ALSA headers (PortAudio: build-essential
# libasound2-dev), dpkg (the notices for the system libraries), and for the AppImage
# appimagetool on PATH (or APPIMAGETOOL=/path/to/it). Build on the oldest distro you
# want to support (CI uses Ubuntu 22.04): the result needs that glibc or newer.
#
#   ./build-linux.sh             app folder + AppImage
#   ./build-linux.sh --no-appimage
#   ./build-linux.sh --clean     start PyInstaller from scratch
set -euo pipefail
cd "$(dirname "$0")"
py="${PYTHON:-.venv/bin/python}"
[ -x "$py" ] || { echo "No .venv: python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt -r requirements-linux.txt" >&2; exit 1; }
clean=(); appimage=1
for a in "$@"; do
  case "$a" in
    --clean) clean=(--clean) ;;
    --no-appimage) appimage=0 ;;
    *) echo "unknown option $a" >&2; exit 2 ;;
  esac
done

# our own PortAudio (ALSA only): the distribution's brings JACK and Berkeley DB along
scripts/build_portaudio.sh

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
    --exclude-module readline --exclude-module dbm --exclude-module _dbm \
    --exclude-module _gdbm \
    --paths . \
    main.py 2>&1 | tee build/pyinstaller.log

# a library PyInstaller couldn't find isn't in the build: the app would start only
# where the user happens to have it (the X11 plugin's libxcb-*, libpulse…)
if grep "Library not found" build/pyinstaller.log; then
  echo "Install the libraries above on this machine so they're bundled, then build again." >&2
  exit 1
fi

"$py" scripts/swap_portaudio.py dist/OnionBoard build/portaudio/libportaudio.so.2

# libraries whose licences the app can't take on must not ship: GPL (readline, gdbm)
# and Berkeley DB (came with JACK)
if ls dist/OnionBoard/_internal | grep -E '^lib(readline|gdbm|db-|jack)'; then
  echo "A library above mustn't ship: exclude what pulls it in." >&2
  exit 1
fi

# pactl (pulseaudio-utils): the device lists, the cable and the mic go through it, and
# Ubuntu 26.04's desktop has none (PipeWire's pulse server, no pulseaudio-utils): the
# app found no speakers or mics. Its libpulse is in the bundle already; the app runs
# the system's pactl when there is one (soundboard/linux/__init__.py: pactl).
# Before the prune: its check makes sure every library pactl needs is in the build
pactl_exe="$(command -v pactl || true)"
[ -n "$pactl_exe" ] || { echo "No pactl here: install pulseaudio-utils so the build ships it." >&2; exit 1; }
mkdir -p dist/OnionBoard/_internal/pactl-bin
cp "$pactl_exe" dist/OnionBoard/_internal/pactl-bin/pactl

# PySide6 brings all of Qt: cut what the app never loads (QML, Quick 3D, translations…)
"$py" scripts/prune_build_linux.py dist/OnionBoard

QT_QPA_PLATFORM=offscreen QTWEBENGINE_DISABLE_SANDBOX="${QTWEBENGINE_DISABLE_SANDBOX:-0}" \
    dist/OnionBoard/OnionBoard --selftest

# add-ons ship with the app, as source (an add-on's environment is made on the user's
# PC by its Install button; inside the AppImage it goes to the data folder). AI voices
# don't, as on Windows (build.ps1): they're an optional download with their voice
# model in it (soundboard/aiaddon.py); shipped without the model, the Voice tab
# offered Install instead of Get, and the install stopped at the model download.
rm -rf dist/OnionBoard/modules
for m in modules/*/; do
  name="$(basename "$m")"
  if [ "$name" = ai-voices ]; then continue; fi
  mkdir -p "dist/OnionBoard/modules/$name"
  (cd "$m" && find . \( -name .venv -o -name __pycache__ \) -prune -o -type f ! -name '*.pyc' ! -name '*.bat' \
     -exec cp --parents {} "../../dist/OnionBoard/modules/$name/" \;)
done

# licences travel with the binaries (Qt is LGPL; see scripts/make_notices.py), and the
# system libraries copied from this machine (scripts/linux_notices.py, needs dpkg).
# readline (GPL) and dbm (Berkeley DB) are left out above: a GUI app needs neither
cp LICENSE dist/OnionBoard/LICENSE.txt
"$py" scripts/linux_notices.py dist/OnionBoard

[ "$appimage" = 1 ] || exit 0
tool="${APPIMAGETOOL:-$(command -v appimagetool || true)}"
[ -n "$tool" ] || { echo "appimagetool not found: set APPIMAGETOOL or use --no-appimage" >&2; exit 1; }
"$py" scripts/make_appdir.py dist/OnionBoard dist/OnionBoard.AppDir
ARCH=x86_64 "$tool" --no-appstream dist/OnionBoard.AppDir dist/OnionBoard-x86_64.AppImage
echo "built dist/OnionBoard-x86_64.AppImage"
