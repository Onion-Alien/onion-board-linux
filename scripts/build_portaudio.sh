#!/usr/bin/env bash
# PortAudio for the Linux build, from its official source, with only the ALSA backend
# (build-linux.sh runs this). The app's streams go through ALSA's "pulse" device
# (soundboard/linux/audio.py). Distributions build PortAudio with JACK too, and their
# libjack brings Berkeley DB, whose licence the app can't take on: this one needs
# libasound alone.
#
#   scripts/build_portaudio.sh      -> build/portaudio/libportaudio.so.2 (+ LICENSE.txt)
#
# Needs git, a C compiler and the ALSA headers (Debian / Ubuntu: build-essential
# libasound2-dev). Built once; delete build/portaudio to build again.
set -euo pipefail
cd "$(dirname "$0")/.."
TAG=v19.7.0
COMMIT=147dd722548358763a8b649b3e4b41dfffbcfbb6   # the tag's commit: a moved tag fails
out=build/portaudio
[ -f "$out/libportaudio.so.2" ] && exit 0
src=build/portaudio-src
rm -rf "$src"
git -c advice.detachedHead=false clone -q --depth 1 --branch "$TAG" \
    https://github.com/PortAudio/portaudio "$src"
got="$(git -C "$src" rev-parse HEAD)"
if [ "$got" != "$COMMIT" ]; then
  echo "PortAudio $TAG is commit $got, expected $COMMIT: not building it" >&2
  exit 1
fi
(cd "$src" && ./configure --quiet --with-alsa --without-jack --without-oss \
    --without-asihpi --disable-static && make -j"$(nproc)" >/dev/null)
mkdir -p "$out"
cp -L "$src/lib/.libs/libportaudio.so.2" "$out/libportaudio.so.2"
cp "$src/LICENSE.txt" "$out/LICENSE.txt"
echo "built $out/libportaudio.so.2 (PortAudio $TAG, ALSA only)"
