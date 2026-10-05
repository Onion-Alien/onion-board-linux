# Linux port: how it's built and where it stands

How complete it is: `docs/LINUX-PROGRESS.md` (`python scripts/linux_progress.py`),
updated after every finished task.

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
fixes upstream made the same way. 1.6.6 (a texts audit) only clashed in the README's
first lines, but reworded two texts the wording table matched: since then
`tests/test_linux_wording.py` also fails when a table entry no longer matches any
upstream text. 1.6.7 (the new voice changer, 8 commits, 37 files) merged with no
conflicts and no new Windows text; its one Windows-only addition, the overlay
preview letting clicks through, got a Linux hook. Before 1.6.8 upstream rewrote
its history (same files, messages and dates, new hashes), so `main..upstream/main`
listed 133 commits, 1.6.6 and 1.6.7 again: the rewritten twin of the last commit
merged (same tree, checked with `git rev-parse <old>^{tree} <new>^{tree}`) was
recorded as merged with `git merge -s ours <twin>`, which changes no file, and
`upstream/main` then merged its 23 new commits. Do the same if it happens again,
only after checking the trees match. 1.6.8 had two conflicts (upstream changed the
last lines of `autostart.py` and `tests/conftest.py`, where the hooks sit), and its
radio fix (no `no_proxy` for FFmpeg) needed the same in `linux/net.py`, which sets
both spellings. 1.6.9 to 1.7.1 (35 commits, 56 files) clashed only where the hooks sit
(the ends of `engine.py` and `voicesdk.py`, the code table in `docs/CODE.md`); the
Apps tab's new folding of shared helpers (Edge WebView, Steam's web helper) got a
Linux process table, and the warning for a Bluetooth headset's call mic a Linux check
(see *Done*). After a merge, grep the new
upstream code for Windows-only calls (`windll`, `WinDLL`, `winreg`, `powershell`,
`.exe`, `CREATE_NO_WINDOW`) and give anything new a Linux hook. New "Windows" text
fails `tests/test_linux_wording.py`, which lists each string: reword it in
`linux/wording.py`, or add it to the test's NOT_ON_LINUX with why it never shows.

## Done

| Area | Linux | Files |
|---|---|---|
| Global hotkeys | X11 key grabs (also games under XWayland), real key-up for hold-to-play, the keyboard grab dropped at once so the game keeps its keys; survives the X server going away. Wayland with no X display: the desktop's GlobalShortcuts portal (KDE Plasma, GNOME 48+) over D-Bus (jeepney): the desktop asks the user once, binds what it allows (the rest show as failed), Activated / Deactivated give press and release. The portal only takes an app id it finds a `.desktop` file for, which an AppImage doesn't install: the app writes a hidden one (`NoDisplay`) to `~/.local/share/applications/onionboard.desktop` before it registers, and names each shortcut in words ("Play Airhorn", "Stop everything"). Checked on Fedora 44 KDE Plasma (Wayland, no X display): the desktop's dialog, hold-to-play (down / up), a changed set of hotkeys asking again for the new one only | `linux/keys.py`, `linux/x11.py`, `linux/portal.py` |
| Key presses (auto push-to-talk) | XTest | `linux/keys.py` |
| Hotkey capture dialog | `winkeys.event_vk()` turns Qt's X keysym into the Windows key code configs store | `winkeys.py`, `settings.py` (one line) |
| MIDI pads | ALSA raw MIDI, busy = EBUSY, unplug detected | `linux/midi.py` |
| Start at login | XDG autostart entry (AppImage path when run from one) | `linux/autostart.py` |
| One copy at a time | flock()ed lock file in `$XDG_RUNTIME_DIR` (the temp folder when that is unset or gone, as seen on WSL), same "come to the front" socket | `linux/singleinstance.py` |
| Data folder | `~/.local/share/OnionBoard` | `linux/__init__.py` |
| Removed sounds | the desktop's Trash | `linux/library.py` |
| Proxy / privacy relay | proxy variables set in both spellings (Linux's environment is case-sensitive), and neither `no_proxy` nor `NO_PROXY` (a radio station redirecting to 127.0.0.1 would step around the relay, as upstream fixed in 1.6.8) | `linux/net.py` |
| Tor | Linux Expert Bundle (pinned SHA-256), bundled libs via `LD_LIBRARY_PATH`, exec bits, `/` in transport paths, distro `tor` as fallback; exits with the app via `__OwningControllerProcess` | `linux/tor.py`, `linux/torget.py` |
| Text-to-speech | eSpeak NG voices (short list: translation languages, English accents, the desktop's language); Piper / voice servers unchanged | `linux/tts.py` |
| Audio devices | the sound server's devices by name (`pactl`); each stream opens on PortAudio's `pulse` device aimed with `PULSE_SINK` / `PULSE_SOURCE`, or where there's none (Fedora doesn't install alsa-plugins-pulseaudio: only PipeWire's own ALSA device) on `pipewire` aimed with `PIPEWIRE_NODE`, never under 40 ms there (it feeds PipeWire's graph a quantum, ~21 ms, at a time: at "low", 8.7 ms, the cable stalled and the speakers dropped out hundreds of times in 10 s on Fedora 44; at 40 ms none); shows as "Onion Board" in volume mixers. Verified end to end on PipeWire and on plain PulseAudio. A device unplugged mid-stream: the sound server quietly moves its stream to the default device (sounds meant for the cable on the speakers) and the watchdog sees no stall, so the engine asks every 2 s (on a thread) whether each stream's device is still there, closes the stream if not ("device not found", as on Windows) and the watchdog's retry reopens it once the device is back; a device that's gone is never opened. Tested by unplugging and replugging a device on a real PulseAudio 16 and PipeWire 1.0.5. On PulseAudio the cable is a null sink, which gives a new stream a few callbacks and then none for 1.6-2 s, and does the same after every underrun: the watchdog (1.5 s) reopened it forever and at "low" buffering busy moments underran it, so the cable carried sound in bursts (found by the WSL "call" test; PipeWire and sound cards don't do it). A stream now gets `START_S` (3 s) from opening before it counts as stalled, and a PulseAudio null sink opens at "high" (Safer, ~0.1 s more delay for listeners). A Bluetooth headset's mic (`bluez_input.…` on PipeWire, `bluez_source.…` on PulseAudio; Linux doesn't name it "Hands-Free") gets upstream's call-quality warning when picked. See `docs/LINUX-AUDIO-SPIKE.md` | `linux/audio.py`, `linux/engine.py` |
| Apps tab and instant replay | PipeWire: each program's stream nodes (`pw-dump`) recorded with `pw-record --target`, several mixed; "everything but Onion Board" for replay. A program's processes are grouped by upstream's rules (`root_pid`) on a table read from `/proc`, with the Linux names of the shared helpers folded into the program that started them (`steamwebhelper`, `QtWebEngineProcess`), never into systemd. Verified on PipeWire. No per-program level meters on Linux (rows show playing / quiet) | `linux/appaudio.py` |
| Virtual cable | made by the app: "Onion Board Cable Input" → "Onion Board Cable Output" (VB-Cable's naming, so the cable detection already works); pactl now, PipeWire drop-in / default.pa for every login. The setup guide's and main window's cable buttons make it (no download, permission or restart) | `linux/vcable.py`, `linux/ui.py` |
| Packaging | `build-linux.sh`: our own PortAudio (ALSA only, see Licences below) → PyInstaller (no `readline` / `dbm`) → fails if a library couldn't be bundled → PortAudio swapped in, JACK / Berkeley DB out → fails if a GPL / Berkeley DB / JACK library is in → `scripts/prune_build_linux.py` → `--selftest` → AppImage (`scripts/make_appdir.py`: AppRun, .desktop, icon painted by the app). The prune follows `prune_build.py`'s rules with ELF `DT_NEEDED` instead of pefile: unused Qt modules and libraries, QML, spare platform plugins (keeps xcb, wayland, offscreen), the touch keyboard, dev tools, translations; 695 → 518 MB unpacked, AppImage 207 MB (Chromium's library alone is 195 MB). Checked here: self-test, and the pruned app running on Xvfb (X11); CI builds it on Ubuntu 22.04 and uploads it as an artifact. A built copy loads the PortAudio it ships (sounddevice only searched the system: without libportaudio2 the AppImage didn't start; `--selftest` now fails on the system's copy). ALSA's and Mesa's libraries (`HOST_LIBS`: libasound, libgbm) are the user's own: libasound finds ALSA's plugins in a folder compiled into it (Ubuntu's, not Fedora's or Arch's), libgbm must match the graphics driver and needed libwayland-server, which wasn't shipped. The prune fails the build if a kept file needs a library that's neither in the build nor one every desktop has (`FROM_SYSTEM`). Both found on a fresh WSL Ubuntu (`docs/LINUX-VM-TEST.md`) | `build-linux.sh`, `scripts/prune_build_linux.py`, `scripts/make_appdir.py` |
| Wording | the app's "Windows" text, reworded as it reaches the screen: Qt's text calls (labels, buttons, tooltips, message boxes, combo items, tabs, tray, clipboard) go through one table. `tests/test_linux_wording.py` fails on any new "Windows" string upstream that's neither reworded nor listed as never shown on Linux. Upstream's own tests see upstream's text (`tests/platform_hooks.py` switches the table off for them) | `linux/wording.py` |
| Voice tab | no Windows voice installs: a language eSpeak has no voice for says to install the distribution's espeak-ng package (or a Piper voice) and keeps Reload voices | `linux/ui.py` |
| Custom voices | Piper's Linux download (`piper/piper` in the voices folder, exec bit given back if lost) or `piper` on PATH; the folder's README in Linux terms | `linux/customvoices.py` |
| Add-ons (live voice) | the add-on's environment is `.venv/bin/python`; inside the AppImage (read-only, a new mount each run) it lives in `~/.local/share/OnionBoard/envs/<add-on>`, so its code comes from the running version and its packages survive updates. Made from the newest `python3` ≥ 3.11 on PATH. `modules/live-voice/install.sh` is the fallback. The build ships the add-ons and the licence files: `scripts/linux_notices.py` adds jeepney and, via dpkg, each bundled system library's package and copyright file | `linux/modules.py`, `build-linux.sh`, `scripts/linux_notices.py` |
| Settings | no "Virtual cable download" switch (nothing is downloaded for the cable); a built copy that can't update itself (a folder build, an AppImage in a folder the user can't write to) says why instead of "runs from source: git pull" | `linux/ui.py`, `linux/wording.py` |
| Self-update | the release's `OnionBoard-x86_64.AppImage` (SHA-256 checked as on Windows); "Restart to update" renames it over the running AppImage (same folder: atomic, the running copy keeps its open file) and a shell starts it once this process is gone (else the single-instance lock sends it back). Only from an AppImage in a writable folder; LD_LIBRARY_PATH as it was before PyInstaller's loader, no AppImage runtime variables | `linux/updates.py` |
| Import from other soundboards | Soundux for Linux's own config (`~/.config/Soundux`, or its Flatpak's), its hotkeys X key codes turned into Windows ones; EXP Soundboard's last board from Java's preferences file; Soundpad and Resanance (and Soundux for Windows) in Wine / Proton prefixes (`$WINEPREFIX`, `~/.wine`, Steam's `compatdata`). A board's Windows paths are found here: `\` turned into `/`, `Z:` is `/`, another drive is that drive in the board's own prefix (else `$WINEPREFIX` / `~/.wine`); a file's name comes out right even when it's missing | `linux/otherboards.py`, `linux/soundux.py`, `linux/expboard.py`, `linux/wine.py` |
| Triggers tab | hidden (not removed: everything that looks it up still finds it), and it never nudges. Onion Watch (its own repo) captures the screen with DXGI / GDI; 0.6.5's module zip does install and load here without errors, but only says it works on Windows. Porting it (X11 capture: XShm, XComposite for one window; a portal on Wayland) is its own project, in that repo; then this tab comes back | `linux/ui.py` |
| Overlay | "The one the game is on" follows the X11 window in front (its middle picks the monitor; `overlay.pick_screen` matches it as on Windows). Upstream only asks on Windows, so `linux/ui.py` patches the overlay's screen choice. A Wayland window in front: its chosen screen. *Show preview* lets clicks through while it's up (upstream: a Windows window style; here Qt's `WindowTransparentForInput`, an empty X11 input shape, checked on Xvfb) | `linux/keys.py`, `linux/voicesdk.py`, `linux/ui.py` |
| Voice engine suggestion | *Who's listening* suggests the game in front's voice engine: the X11 active window (`_NET_ACTIVE_WINDOW`, so games under XWayland too) → `_NET_WM_PID` → a Proton / Wine game's .exe from its command line (`Z:\` is `/`, another drive in its `WINEPREFIX`), a native program's `/proc/<pid>/exe`; the scan is upstream's. Desktop and Wine programs (`/usr`, `C:\windows`) don't count. A native libvivoxsdk.so isn't looked for; Wayland windows give nothing | `linux/voicesdk.py`, `linux/x11.py`, `linux/ui.py` |
| "✓ done" labels | a label wider than the one it replaced now gets its room (showed with Linux fonts) | `ui/busy.py` |
| Tests | `tests/test_linux_*.py`; `tests/platform_hooks.py` skips tests of Windows itself (each with its reason) and guards real MIDI / autostart / sound server. Upstream's suite runs on 4 workers (pytest-xdist); each test's Xvfb picks a free display itself (`-displayfd`) and each dbus-daemon has its own address, so workers never share one. The tests never see the desktop's own `DISPLAY` / `WAYLAND_DISPLAY` (`tests/platform_hooks.py`): run from a desktop, the apps tests made grabbed hotkeys on the real X server and their leftover hotkey threads segfaulted later tests | |
| Dependencies | `requirements-linux.txt` = `requirements.txt` + jeepney (kept apart so upstream merges never touch `requirements.txt`) | |
| CI | `.github/workflows/linux.yml`: tests on Ubuntu 24.04 (Xvfb with keymap), the AppImage on 22.04, and on a published release the AppImage attached to it. `checks.yml` runs the Windows tests | |
| Download links | README (*Download*, *On Linux*) and the website: `releases/latest/download/OnionBoard-x86_64.AppImage` | `README.md`, `docs/index.html` |

## Next, in order

1. **Audio devices on real hardware.** On a real sound server here (PulseAudio 16,
   null sinks as devices): the cable end to end, made at login from `default.pa`,
   and a device unplugged mid-stream and plugged back (see *Audio devices* above).
   Left for a real desktop: a real USB headset on PipeWire (WirePlumber may move a
   stream back by itself; the watchdog copes either way), and a device never seen
   before being plugged in (the lists are re-read on `engine.rescan()`).
2. **Setup guide on a real desktop.** Every guide page (before and after *Make it
   now*), the Steam help, every Settings page and every main tab were rendered here
   offscreen against a private PipeWire with made-up devices and read through: the
   leftovers (VB-Cable's "CABLE Output", "by the clock", "install the free virtual
   cable", the Onion Watch card) are reworded or hidden, and
   `tests/test_linux_wording.py` now also catches VB-Cable / "CABLE …" text and only
   skips the guide's installer strings, not the whole guide. Left: clicking through
   it on a real desktop with a real Discord.
3. **Wayland without XWayland on GNOME 48+** (done on KDE Plasma, see *Done*), and
   whether the overlay's *Show preview* lets clicks through on native Wayland (the
   overlay is X11 / XWayland only).
3a. **Drop-outs with the whole app at "low"**: the engine alone has none, the window
   running adds some (21 in 40 s on WSLg's speakers through "pulse"; a few at start
   on Fedora's PipeWire at 40 ms). The window's work on the main thread holding up
   the audio callbacks is the likely cause (the GIL); not yet pinned down.
4. **Who's listening: the program recording the cable.** 1.7.0 names the program
   that records the cable's far end and can switch the mode by itself
   (`voicesdk.Listeners`, `appaudio.recording_apps`); upstream only starts it on
   Windows (`MainWindow.listeners` is None elsewhere). On Linux it would read
   PipeWire's `Stream/Input/Audio` nodes aimed at "Onion Board Cable Output", with the
   Linux names of the voice apps (`Discord`, `teamspeak3`, `mumble`, browsers).
5. **Release**: ready for the first one after launch. Publishing a release runs
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

## The test-suite segfault (found, fixed)

An intermittent segfault in full runs (first seen near `test_net_leaks.py`, later
under `test_ytdl.py::test_searching_shows_a_centred_mascot_then_the_results`, about
one run in four once the suite ran on 4 workers) was caught with `python -X
faulthandler`: the crashing thread was `ytsearch.SearchResults._work` emitting its
result. `test_ytdl.py::test_results_spin_while_searching_and_offer_every_site`
started a second search, closed the panel and returned; the search thread then
emitted on the freed widget during a later test. The test now waits for its
`web-search` thread (a test bug only: the app's panel lives as long as its window).
It's in upstream's test, so it's worth sending upstream too. Five full runs since:
clean. The same loops found a real flake earlier, also fixed: the test proxy's pipe
thread raising ValueError on Linux when its socket was closed under it. Another
upstream test fix to send back: `test_bunnywidget.py`'s frames added the real time
each paint took to the pretend 35 ms, so on a slower machine (CI, once) the hammer
act ended in the 50 ms between one blow's sawdust fading and the next blow; it now
steps exactly 35 ms a frame. A fourth, from 1.7.x: `test_radio.py`'s
`test_filter_boxes_wrap_instead_of_cutting_their_words` measured the filter boxes
without the app's style sheet unless an earlier test in the same process had applied
it, so run alone (or first on a worker) it failed every time; it applies the theme
itself now. A third, from 1.6.8: `test_audit_net.py`'s
`test_a_cut_update_download_says_why_in_plain_words` switched the connection 0.3 s
after a timer started before the download, so on a slow runner (this repo's Windows
CI, once) the switch came first, the download went direct and couldn't look up the
proxy's own `slow.test`; the timer now starts once the download is open.

## Checking on a real Linux desktop

`docs/LINUX-VM-TEST.md` is a ready prompt for Claude Code on a Windows PC: WSL 2 with
the AppImage, the cable on PulseAudio and PipeWire, the window, and a localhost
"call" (the Linux app's cable → Opus → the Windows desktop, pads pressed from Windows
through the Remote API), then a Fedora KDE VM for Wayland hotkeys and Discord.

`python scripts/linux_audio_check.py` makes the cable, plays a quiet beep through the
real engine into "Onion Board Cable Input" and checks it comes out of "Onion Board
Cable Output" (what Discord hears). Nothing goes to the speakers. `--remove` takes a
cable it made away again. It waits for the recording to flow before it plays:
PulseAudio's null sink takes up to ~2 s to start feeding a new recording (a call in
progress isn't affected).

## Running the tests here

```
python -m pytest                      # QT_QPA_PLATFORM=offscreen comes from conftest
```

The whole suite runs on 4 workers (pytest-xdist, `-n auto` in pyproject, about 75 s
here); one or two files run in one process; `-n 0` turns the workers off.

The overlay preview's X11 check runs the app on a private Xvfb with Qt's xcb
plugin, which needs `libxcb-icccm4` and `libxcb-keysyms1` (skipped without them).

WSLg mounts `/tmp/.X11-unix` read-only, so Xvfb can't make its socket there
(`tests/xvfb.py` fails at once saying so). Run the tests in a mount namespace with
a tmpfs there, as yourself:

```
unshare -rm sh -c "mount -t tmpfs tmpfs /tmp/.X11-unix && \
  exec unshare -U --map-user=$(id -u) --map-group=$(id -g) -- python -m pytest"
```

WSL's mirrored networking drops a connection to a closed loopback port instead of
refusing it, so tests that expect "connection refused" wait out their timeout there
(`test_customvoices.py::test_server_errors_say_what_happened` takes 60 s); a real
Linux refuses at once.

As root (containers), Chromium needs `QTWEBENGINE_DISABLE_SANDBOX=1` or the radio
globe test aborts the run. A machine whose own `https_proxy` / `no_proxy` are set can
fail `test_net.py`'s environment tests: unset them for the run.
