#!/bin/sh
# Fallback installer: Onion Board's Voice tab has an Install button that does the same.
# Needs Python 3.12+ with venv (Debian / Ubuntu: sudo apt install python3-venv).
# About 90 MB with the voice model.
#   ./install.sh --quiet   no "press Enter" at the end
cd "$(dirname "$0")" || exit 1
fail() {
  echo
  echo "Install failed - see the messages above."
  [ "$1" = "--quiet" ] || { printf "Press Enter to close. "; read -r _; }
  exit 1
}
PY=""
for p in python3.14 python3.13 python3.12 python3; do
  if command -v "$p" >/dev/null 2>&1 &&
     "$p" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
    PY="$p"; break
  fi
done
[ -n "$PY" ] || { echo "Python 3.12 or newer wasn't found."; fail "$1"; }
# its own environment: .venv here, or in Onion Board's data folder when this folder
# can't be written (inside the AppImage), where the app looks for it too
ENV=.venv
[ -w . ] || ENV="${XDG_DATA_HOME:-$HOME/.local/share}/OnionBoard/envs/$(basename "$PWD")"
if [ ! -x "$ENV/bin/python" ]; then
  mkdir -p "$(dirname "$ENV")" && "$PY" -m venv "$ENV" || fail "$1"
fi
"$ENV/bin/python" -m pip install --disable-pip-version-check -r requirements.txt || fail "$1"
"$ENV/bin/python" helper.py --download || fail "$1"
echo
echo "AI voices are installed. Press Refresh in Onion Board's Voice tab."
[ "$1" = "--quiet" ] || { printf "Press Enter to close. "; read -r _; }
exit 0
