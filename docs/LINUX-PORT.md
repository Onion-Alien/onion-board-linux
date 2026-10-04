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
(set its push URL to something invalid, e.g. `git remote set-url --push upstream
DISABLED`: nothing of the port goes public before launch), then
`git fetch upstream main && git merge upstream/main`. The first release merged this
way (21 commits, 35 files) went in with no conflicts; 1.6.5 (21 commits, with
importing from other soundboards) had three small ones: the README's code layout
moved to `docs/CODE.md` (the `soundboard/linux/` row went with it) and two test
fixes upstream made the same way. After a merge, grep the new
upstream code for Windows-only calls (`windll`, `WinDLL`, `winreg`, `powershell`,
`.exe`, `CREATE_NO_WINDOW`) and give anything new a Linux hook. New "Windows" text
fails `tests/test_linux_wording.py`, which lists each string: reword it in
`linux/wording.py`, or add it to the test's NOT_ON_LINUX with why it never shows.

## Done

| Area | Linux | Files |
|---|---|---|
| Global hotkeys | X11 key grabs (also games under XWayland), real key-up for hold-to-play, the keyboard grab dropped at once so the game keeps its keys; survives the X server going away. Wayland with no X display: the desktop's GlobalShortcuts portal (KDE Plasma, GNOME 48+) over D-Bus (jeepney): the desktop asks the user once, binds what it allows (the rest show as failed), Activated / Deactivated give press and release. Tested against a stand-in portal on a private dbus-daemon, not yet on a real desktop | `linux/keys.py`, `linux/x11.py`, `linux/portal.py` |
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
| Virtual cable | made by the app: "Onion Board Cable Input" → "Onion Board Cable Output" (VB-Cable's naming, so the cable detection already works); pactl now, PipeWire drop-in / default.pa for every login. The setup guide's and main window's cable buttons make it (no download, permission or restart) | `linux/vcable.py`, `linux/ui.py` |
| Packaging | `build-linux.sh`: our own PortAudio (ALSA only, see Licences below) → PyInstaller (no `readline` / `dbm`) → fails if a library couldn't be bundled → PortAudio swapped in, JACK / Berkeley DB out → fails if a GPL / Berkeley DB / JACK library is in → `scripts/prune_build_linux.py` → `--selftest` → AppImage (`scripts/make_appdir.py`: AppRun, .desktop, icon painted by the app). The prune follows `prune_build.py`'s rules with ELF `DT_NEEDED` instead of pefile: unused Qt modules and libraries, QML, spare platform plugins (keeps xcb, wayland, offscreen), the touch keyboard, dev tools, translations; 695 → 518 MB unpacked, AppImage 207 MB (Chromium's library alone is 195 MB). Checked here: self-test, and the pruned app running on Xvfb (X11); CI builds it on Ubuntu 22.04 and uploads it as an artifact | `build-linux.sh`, `scripts/prune_build_linux.py`, `scripts/make_appdir.py` |
| Wording | the app's "Windows" text, reworded as it reaches the screen: Qt's text calls (labels, buttons, tooltips, message boxes, combo items, tabs, tray, clipboard) go through one table. `tests/test_linux_wording.py` fails on any new "Windows" string upstream that's neither reworded nor listed as never shown on Linux. Upstream's own tests see upstream's text (`tests/platform_hooks.py` switches the table off for them) | `linux/wording.py` |
| Voice tab | no Windows voice installs: a language eSpeak has no voice for says to install the distribution's espeak-ng package (or a Piper voice) and keeps Reload voices | `linux/ui.py` |
| Custom voices | Piper's Linux download (`piper/piper` in the voices folder, exec bit given back if lost) or `piper` on PATH; the folder's README in Linux terms | `linux/customvoices.py` |
| Add-ons (live voice) | the add-on's environment is `.venv/bin/python`; inside the AppImage (read-only, a new mount each run) it lives in `~/.local/share/OnionBoard/envs/<add-on>`, so its code comes from the running version and its packages survive updates. Made from the newest `python3` ≥ 3.11 on PATH. `modules/live-voice/install.sh` is the fallback. The build ships the add-ons and the licence files: `scripts/linux_notices.py` adds jeepney and, via dpkg, each bundled system library's package and copyright file | `linux/modules.py`, `build-linux.sh`, `scripts/linux_notices.py` |
| Settings | no "Virtual cable download" switch (nothing is downloaded for the cable); a built copy that can't update itself (a folder build, an AppImage in a folder the user can't write to) says why instead of "runs from source: git pull" | `linux/ui.py`, `linux/wording.py` |
| Self-update | the release's `OnionBoard-x86_64.AppImage` (SHA-256 checked as on Windows); "Restart to update" renames it over the running AppImage (same folder: atomic, the running copy keeps its open file) and a shell starts it once this process is gone (else the single-instance lock sends it back). Only from an AppImage in a writable folder; LD_LIBRARY_PATH as it was before PyInstaller's loader, no AppImage runtime variables | `linux/updates.py` |
| Import from other soundboards | Soundux for Linux's own config (`~/.config/Soundux`, or its Flatpak's), its hotkeys X key codes turned into Windows ones; EXP Soundboard's last board from Java's preferences file; Soundpad and Resanance (and Soundux for Windows) in Wine / Proton prefixes (`$WINEPREFIX`, `~/.wine`, Steam's `compatdata`). A board's Windows paths are found here: `\` turned into `/`, `Z:` is `/`, another drive is that drive in the board's own prefix (else `$WINEPREFIX` / `~/.wine`); a file's name comes out right even when it's missing | `linux/otherboards.py`, `linux/soundux.py`, `linux/expboard.py`, `linux/wine.py` |
| Voice engine suggestion | *Who's listening* suggests the game in front's voice engine: the X11 active window (`_NET_ACTIVE_WINDOW`, so games under XWayland too) → `_NET_WM_PID` → a Proton / Wine game's .exe from its command line (`Z:\` is `/`, another drive in its `WINEPREFIX`), a native program's `/proc/<pid>/exe`; the scan is upstream's. Desktop and Wine programs (`/usr`, `C:\windows`) don't count. A native libvivoxsdk.so isn't looked for; Wayland windows give nothing | `linux/voicesdk.py`, `linux/x11.py`, `linux/ui.py` |
| "✓ done" labels | a label wider than the one it replaced now gets its room (showed with Linux fonts) | `ui/busy.py` |
| Tests | `tests/test_linux_*.py`; `tests/platform_hooks.py` skips tests of Windows itself (each with its reason) and guards real MIDI / autostart / sound server. Upstream's suite runs on 4 workers (pytest-xdist); each test's Xvfb picks a free display itself (`-displayfd`) and each dbus-daemon has its own address, so workers never share one | |
| Dependencies | `requirements-linux.txt` = `requirements.txt` + jeepney (kept apart so upstream merges never touch `requirements.txt`) | |
| CI | `.github/workflows/linux.yml`: tests on Ubuntu 24.04 (Xvfb with keymap), the AppImage on 22.04, and on a published release the AppImage attached to it. `checks.yml` runs the Windows tests | |
| Download links | README (*Download*, *On Linux*) and the website: `releases/latest/download/OnionBoard-x86_64.AppImage` | `README.md`, `docs/index.html` |

## Next, in order

1. **Audio devices: hot-plug and edge cases.** Lists are re-read on `engine.rescan()`;
   check plugging a headset in and out with the app running, a device that vanishes
   mid-stream (PipeWire may move the stream to the default device), and plain
   PulseAudio (only PipeWire was tested).
2. **Setup guide on a real desktop.** The cable buttons make the cable and the
   wording table covers the text; try the whole guide once (`python -m soundboard`,
   after asking: it opens windows), including the Discord page and the Steam help.
3. **Wayland without XWayland, on a real desktop**: try the portal hotkeys on KDE
   Plasma and GNOME 48+ (first bind shows the desktop's dialog; check hold-to-play
   and a changed set of hotkeys). The overlay is X11 / XWayland only.
4. **Release**: ready for the first one after launch. Publishing a release runs
   `linux.yml`, which builds the AppImage from the tag and attaches it as
   `OnionBoard-x86_64.AppImage` (job `release`); the README and the website link
   `releases/latest/download/OnionBoard-x86_64.AppImage`, and DEVELOPING.md's release
   steps say so. Not yet tried on a real release (this repo has none).

## Licences in the Linux build

The AppImage carries system libraries from the build machine; THIRD-PARTY-NOTICES.txt
has each one's package and copyright file (`scripts/linux_notices.py`). Two kinds
are kept out on purpose, and `build-linux.sh` fails if one gets back in:

- GPL libraries: Python's `readline` and `dbm` modules (libreadline, libgdbm) are
  excluded; a GUI app uses neither.
- Berkeley DB (`libdb`) and JACK: the distribution's PortAudio links JACK, which
  links Berkeley DB, whose licence the app can't take on. `scripts/build_portaudio.sh`
  builds PortAudio 19.7.0 from its official source (MIT, pinned tag and commit)
  with only the ALSA backend the app uses, and `scripts/swap_portaudio.py` puts it in
  and removes what only the old copy needed.

## Known test-suite issue

An intermittent segfault was seen once in a full run near
`tests/test_net_leaks.py::test_radio_directory_through_the_proxy`. Not reproduced
since: 5 full runs and 8 runs of `test_mainwindow` … `test_net_switches`, all with
`python -X faulthandler`. If it shows again, keep the faulthandler dump: the
"Current thread" stack says which thread crashed (a Qt object freed off the UI
thread is the usual suspect). The same loops found a real flake, fixed: the test
proxy's pipe thread raising ValueError on Linux when its socket was closed under it.

## Checking on a real Linux desktop

`docs/LINUX-VM-TEST.md` is a ready prompt for Claude Code on a Windows PC: WSL 2 with
the AppImage, the cable on PulseAudio and PipeWire, the window, and a localhost
"call" (the Linux app's cable → Opus → the Windows desktop, pads pressed from Windows
through the Remote API), then a Fedora KDE VM for Wayland hotkeys and Discord.

`python scripts/linux_audio_check.py` makes the cable, plays a quiet beep through the
real engine into "Onion Board Cable Input" and checks it comes out of "Onion Board
Cable Output" (what Discord hears). Nothing goes to the speakers. `--remove` takes a
cable it made away again.

## Running the tests here

```
python -m pytest                      # QT_QPA_PLATFORM=offscreen comes from conftest
```

The whole suite runs on 4 workers (pytest-xdist, `-n auto` in pyproject, about 75 s
here); one or two files run in one process; `-n 0` turns the workers off.

As root (containers), Chromium needs `QTWEBENGINE_DISABLE_SANDBOX=1` or the radio
globe test aborts the run. A machine whose own `https_proxy` / `no_proxy` are set can
fail `test_net.py`'s environment tests: unset them for the run.
