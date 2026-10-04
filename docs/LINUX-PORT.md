# Linux port: how it's built and where it stands

Private until launch. This repo is `main` of the public repo plus the port; upstream
releases are merged in (never rebased), and at launch it merges back as one codebase
with a Linux download next to the Windows one.

## Keeping upstream merges painless

The Windows modules keep their upstream code. Each one the port touches gets two
small hooks and nothing else:

- **top**: a Windows DLL becomes `win_dll(...)` (a `NoDLL` stand-in off Windows), so
  the module still imports and its portable parts (tables, parsing) still work
- **bottom**: `from soundboard.linux.<name> import *` replaces the Windows-only
  functions and classes with the Linux ones (each Linux module has an `__all__`)

Linux code lives in `soundboard/linux/`. A Linux module that needs its Windows
module looks it up lazily (`_w()`, `_t()`, …): the Windows module star-imports it at
its end, so importing it at the top would get a half-loaded copy.

`soundboard/app.py` imports `soundboard.linux` first thing; off Windows that sets
`APPDATA` to the XDG data folder, so every `%APPDATA%\OnionBoard` path in the app is
`~/.local/share/OnionBoard` without touching those modules.

Upstream: `git remote add upstream https://github.com/Onion-Alien/onion-board.git`
(push to it is disabled in the working copy), then `git fetch upstream main &&
git merge upstream/main`.

## Done

| Area | Linux | Files |
|---|---|---|
| Global hotkeys | X11 key grabs (also games under XWayland), real key-up for hold-to-play, the keyboard grab dropped at once so the game keeps its keys; survives the X server going away | `linux/keys.py`, `linux/x11.py` |
| Key presses (auto push-to-talk) | XTest | `linux/keys.py` |
| Hotkey capture dialog | `winkeys.event_vk()` turns Qt's X keysym into the Windows key code configs store | `winkeys.py`, `settings.py` (one line) |
| MIDI pads | ALSA raw MIDI, busy = EBUSY, unplug detected | `linux/midi.py` |
| Start at login | XDG autostart entry (AppImage path when run from one) | `linux/autostart.py` |
| One copy at a time | flock()ed lock file, same "come to the front" socket | `linux/singleinstance.py` |
| Data folder | `~/.local/share/OnionBoard` | `linux/__init__.py` |
| Removed sounds | the desktop's Trash | `linux/library.py` |
| Proxy / privacy relay | proxy variables set in both spellings (Linux's environment is case-sensitive) | `linux/net.py` |
| Tor | Linux Expert Bundle (pinned SHA-256), bundled libs via `LD_LIBRARY_PATH`, exec bits, `/` in transport paths, distro `tor` as fallback; exits with the app via `__OwningControllerProcess` | `linux/tor.py`, `linux/torget.py` |
| Text-to-speech | eSpeak NG voices (short list: translation languages, English accents, the desktop's language); Piper / voice servers unchanged | `linux/tts.py` |
| Audio devices | the sound server's devices by name (`pactl`); each stream opens on PortAudio's `pulse` device aimed with `PULSE_SINK` / `PULSE_SOURCE`; shows as "Onion Board" in volume mixers. Verified end to end on PipeWire. See `docs/LINUX-AUDIO-SPIKE.md` | `linux/audio.py`, `linux/engine.py` |
| Apps tab and instant replay | PipeWire: each program's stream nodes (`pw-dump`) recorded with `pw-record --target`, several mixed; "everything but Onion Board" for replay. Verified on PipeWire. No per-program level meters on Linux (rows show playing / quiet) | `linux/appaudio.py` |
| Virtual cable | made by the app: "Onion Board Cable Input" → "Onion Board Cable Output" (VB-Cable's naming, so the cable detection already works); pactl now, PipeWire drop-in / default.pa for every login | `linux/vcable.py` (not wired into the UI yet) |
| "✓ done" labels | a label wider than the one it replaced now gets its room (showed with Linux fonts) | `ui/busy.py` |
| Tests | `tests/test_linux_*.py`; `tests/platform_hooks.py` skips tests of Windows itself (each with its reason) and guards real MIDI / autostart / sound server | |
| CI | `.github/workflows/linux.yml` (Ubuntu 24.04, Xvfb with keymap) | |

## Next, in order

1. **Audio devices: hot-plug and edge cases.** Lists are re-read on `engine.rescan()`;
   check plugging a headset in and out with the app running, a device that vanishes
   mid-stream (PipeWire may move the stream to the default device), and plain
   PulseAudio (only PipeWire was tested).
2. **Setup guide and the cable in the UI.** The VB-Cable install step becomes "Make the
   virtual cable" (`vcable.install()`), its restart / permission steps go, Discord's
   input becomes "Onion Board Cable Output". `tests/platform_hooks.py` lists the
   VB-Cable tests skipped until then.
3. **Wording.** ~70 strings say "Windows" (Start with Windows, Windows voices, Task
   Manager…). Plan: one table of Windows → Linux wording applied in one place, not
   edits all over the upstream files.
4. **Windows-only features to hide on Linux**: Windows voice installs
   (`speech/winvoices.py`), shell icon / taskbar (`shellicon.py`), the VB-Cable 48 kHz
   fix (`cableformat.py`), `voicesdk.py` (use `/proc/<pid>/exe`; Proton games are
   Windows exes, so the checks mostly still apply).
5. **Packaging**: PyInstaller on Linux → AppImage built on Ubuntu 22.04 in CI
   (`--selftest` after), a Linux `prune_build.py`, self-update replacing the AppImage
   (`updates.py`), `live-voice` add-on `install.sh`.
6. **Wayland without XWayland**: the GlobalShortcuts portal for hotkeys; the overlay is
   X11 / XWayland only.

## Checking on a real Linux desktop

`python scripts/linux_audio_check.py` makes the cable, plays a quiet beep through the
real engine into "Onion Board Cable Input" and checks it comes out of "Onion Board
Cable Output" (what Discord hears). Nothing goes to the speakers. `--remove` takes a
cable it made away again.

## Running the tests here

```
python -m pytest                      # QT_QPA_PLATFORM=offscreen comes from conftest
```

As root (containers), Chromium needs `QTWEBENGINE_DISABLE_SANDBOX=1` or the radio
globe test aborts the run. A machine whose own `https_proxy` / `no_proxy` are set can
fail `test_net.py`'s environment tests: unset them for the run.
