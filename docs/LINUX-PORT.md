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
(see *Done*). 1.7.2 to 1.8.0 (41 commits, 136 files: AI voices, the clip editor) clashed only at `library.py`'s end, where the hook sits; the AI voices add-on got an `install.sh`, and its pinned numpy (2.5, also live voice's) needs Python 3.12, so the add-ons' minimum went from 3.11 to 3.12. Three of its tests are Windows-only (listed in `tests/platform_hooks.py`). 1.8.1 to 1.9.1 (63 commits, 114 files: *Straight into my mic*, the simpler sound modes, the anonymous usage count) merged with no conflicts. The mic effect (`directmic.py`) is Windows' own (a capture APO in the registry, put on the mic with an admin prompt), so for now Linux runs as before it: `import winreg` became optional at its top and `linux/directmic.py` answers "not on any mic" at its end; `linux/library.py` takes `mic` out of the routes (a first start, 1.9.1's one-time move off the cable and a saved `mic` all land on the cable; a saved value is still written back as it was), and `linux/ui.py` hides the mic's choice and buttons and What's new's mic notes. Two more needed hooks: the Apps tab's capture gained `start(wait=False)` / `stop(wait=False)` / `join()` / `ready` (a capture slow to open mustn't freeze the window) and `appaudio.running()` (a quiet program isn't a closed one), which the Linux capture now has too; and *Update now* prefers a release's `OnionBoardSetup-update.exe` (counted apart from new downloads), which Linux would have fetched: Linux's is `OnionBoard-x86_64-update.AppImage`, attached by the release job next to the AppImage, else the AppImage itself. After a merge, grep the new
upstream code for Windows-only calls (`windll`, `WinDLL`, `winreg`, `powershell`,
`.exe`, `CREATE_NO_WINDOW`, `netsh`, `sys.platform`, `ProgramData`) and give anything new a Linux hook, and check every function a Linux module replaces still takes upstream's arguments (the capture's `wait` was found only by the suite). New "Windows" text
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
| Secure connections | a built copy carries the build machine's OpenSSL (Ubuntu's), which looks for the certificate authorities in `/usr/lib/ssl`; Fedora keeps them under `/etc/pki`, so on Fedora 44 every HTTPS connection (update check, radio, voice downloads) failed with "certificate verify failed". At start, when OpenSSL's own place has none, `SSL_CERT_FILE` (or `SSL_CERT_DIR`) points at the distribution's bundle (Debian / Ubuntu / Arch, Fedora / RHEL, openSUSE, Alpine paths), read by Python, Qt and FFmpeg alike; a user's own setting is kept. Checked on Fedora 44: the update check fails without it and works with it | `linux/__init__.py` |
| Tor | Linux Expert Bundle (pinned SHA-256), bundled libs via `LD_LIBRARY_PATH`, exec bits, `/` in transport paths, distro `tor` as fallback; exits with the app via `__OwningControllerProcess` | `linux/tor.py`, `linux/torget.py` |
| Text-to-speech | eSpeak NG voices (short list: translation languages, English accents, the desktop's language); Piper / voice servers unchanged | `linux/tts.py` |
| Audio devices | the sound server's devices by name (`pactl`); each stream opens on PortAudio's `pulse` device aimed with `PULSE_SINK` / `PULSE_SOURCE`, or where there's none (Fedora doesn't install alsa-plugins-pulseaudio: only PipeWire's own ALSA device) on `pipewire` aimed with `PIPEWIRE_NODE`, never under 40 ms there (it feeds PipeWire's graph a quantum, ~21 ms, at a time: at "low", 8.7 ms, the cable stalled and the speakers dropped out hundreds of times in 10 s on Fedora 44; at 40 ms none); shows as "Onion Board" in volume mixers. Verified end to end on PipeWire and on plain PulseAudio. A device unplugged mid-stream: the sound server quietly moves its stream to the default device (sounds meant for the cable on the speakers) and the watchdog sees no stall, so the engine asks (on a thread) whether each stream's device is still there whenever the sound server reports a device coming or going (one `pactl subscribe` kept open, ended by a shell when the app's side closes, so a crash leaves nothing behind; it used to ask every 2 s, and each `pactl list` stalled every stream ~20 ms on PulseAudio: WSLg's at "low" underran 30 times in 45 s with the app open, 4 now, all at start, as with the engine alone; every 2 s again if the watcher can't run), closes the stream if not ("device not found", as on Windows) and the watchdog's retry reopens it once the device is back; a device that's gone is never opened. Tested by unplugging and replugging a device on a real PulseAudio 16 and PipeWire 1.0.5. On PulseAudio the cable is a null sink, which gives a new stream a few callbacks and then none for 1.6-2 s, and does the same after every underrun: the watchdog (1.5 s) reopened it forever and at "low" buffering busy moments underran it, so the cable carried sound in bursts (found by the WSL "call" test; PipeWire and sound cards don't do it). A stream now gets `START_S` (3 s) from opening before it counts as stalled, and a PulseAudio null sink opens at "high" (Safer, ~0.1 s more delay for listeners). A Bluetooth headset's mic (`bluez_input.…` on PipeWire, `bluez_source.…` on PulseAudio; Linux doesn't name it "Hands-Free") gets upstream's call-quality warning when picked. See `docs/LINUX-AUDIO-SPIKE.md` | `linux/audio.py`, `linux/engine.py` |
| Apps tab and instant replay | PipeWire: each program's stream nodes (`pw-dump`) recorded with `pw-record --target`, several mixed; a capture starts and stops without waiting (upstream 1.9), and a quiet program whose process still runs keeps its row (`running()` from `/proc`); "everything but Onion Board" for replay. A program's processes are grouped by upstream's rules (`root_pid`) on a table read from `/proc`, with the Linux names of the shared helpers folded into the program that started them (`steamwebhelper`, `QtWebEngineProcess`), never into systemd. Verified on PipeWire. No per-program level meters on Linux (rows show playing / quiet) | `linux/appaudio.py` |
| Virtual cable | made by the app: "Onion Board Cable Input" → "Onion Board Cable Output" (VB-Cable's naming, so the cable detection already works); pactl now, PipeWire drop-in / default.pa for every login. The setup guide's and main window's cable buttons make it (no download, permission or restart) | `linux/vcable.py`, `linux/ui.py` |
| Packaging | `build-linux.sh`: our own PortAudio (ALSA only, see Licences below) → PyInstaller (no `readline` / `dbm`) → fails if a library couldn't be bundled → PortAudio swapped in, JACK / Berkeley DB out → fails if a GPL / Berkeley DB / JACK library is in → `scripts/prune_build_linux.py` → `--selftest` → AppImage (`scripts/make_appdir.py`: AppRun, .desktop, icon painted by the app). The prune follows `prune_build.py`'s rules with ELF `DT_NEEDED` instead of pefile: unused Qt modules and libraries, QML, spare platform plugins (keeps xcb, wayland, offscreen), the touch keyboard, dev tools, translations; 695 → 518 MB unpacked, AppImage 207 MB (Chromium's library alone is 195 MB). Checked here: self-test, and the pruned app running on Xvfb (X11); CI builds it on Ubuntu 22.04 and uploads it as an artifact. A built copy loads the PortAudio it ships (sounddevice only searched the system: without libportaudio2 the AppImage didn't start; `--selftest` now fails on the system's copy). ALSA's and Mesa's libraries (`HOST_LIBS`: libasound, libgbm) are the user's own: libasound finds ALSA's plugins in a folder compiled into it (Ubuntu's, not Fedora's or Arch's), libgbm must match the graphics driver and needed libwayland-server, which wasn't shipped. So is the C++ runtime (libstdc++, libgcc_s): the build's (Ubuntu 22.04's) loaded first kept Fedora 44's Mesa from loading (GLIBCXX_3.4.32 not found), so Qt had no OpenGL and the AppImage's window never drew on Fedora (found 2026-10-06; earlier Fedora checks were headless or counted underruns, so nobody looked at the window); every system the app runs on has one at least as new. Checked with the CI AppImage of 57cf37a on Fedora: the window draws at once, no OpenGL errors. With the window drawing, the Fedora VM counts drop-outs again (about 2 a minute idle at "low", dozens while clicking around; the VM renders with software OpenGL on 2 cores): which stream, and whether a real PC does it too, is open (the dropouts-window row). The prune fails the build if a kept file needs a library that's neither in the build nor one every desktop has (`FROM_SYSTEM`). Both found on a fresh WSL Ubuntu (`docs/LINUX-VM-TEST.md`) | `build-linux.sh`, `scripts/prune_build_linux.py`, `scripts/make_appdir.py` |
| Wording | the app's "Windows" text, reworded as it reaches the screen: Qt's text calls (labels, buttons, tooltips, message boxes, combo items, tabs, tray, clipboard) go through one table. `tests/test_linux_wording.py` fails on any new "Windows" string upstream that's neither reworded nor listed as never shown on Linux. Upstream's own tests see upstream's text (`tests/platform_hooks.py` switches the table off for them) | `linux/wording.py` |
| Voice tab | no Windows voice installs: a language eSpeak has no voice for says to install the distribution's espeak-ng package (or a Piper voice) and keeps Reload voices | `linux/ui.py` |
| Custom voices | Piper's Linux download (`piper/piper` in the voices folder, exec bit given back if lost) or `piper` on PATH; the folder's README in Linux terms | `linux/customvoices.py` |
| Add-ons (live voice, AI voices) | the add-on's environment is `.venv/bin/python`; inside the AppImage (read-only, a new mount each run) it lives in `~/.local/share/OnionBoard/envs/<add-on>`, so its code comes from the running version and its packages survive updates. So does an unpacked AppImage's (`--appimage-extract-and-run`, or no FUSE: writable but temporary; `_in_appimage`). The system's python3 is run with the user's own library path (`linux.host_env()`, through `net.child_env`): with PyInstaller's, pointing at the bundle, Fedora 44's `python3.14 -m venv` failed setting up pip, so AI voices didn't install from the AppImage. Made from the newest `python3` ≥ 3.12 on PATH (the add-ons pin numpy 2.5, which needs 3.12: a 3.11, Debian 12's, failed halfway through pip). `modules/<add-on>/install.sh` is the fallback (the Linux twin of each `install.bat`). The build ships the add-ons and the licence files: `scripts/linux_notices.py` adds jeepney and, via dpkg, each bundled system library's package and copyright file | `linux/modules.py`, `build-linux.sh`, `scripts/linux_notices.py` |
| Settings | no "Virtual cable download" switch (nothing is downloaded for the cable); a built copy that can't update itself (a folder build, an AppImage in a folder the user can't write to) says why instead of "runs from source: git pull" | `linux/ui.py`, `linux/wording.py` |
| Self-update | the release's `OnionBoard-x86_64-update.AppImage` (1.9.1's update copy, counted apart from new downloads), else its `OnionBoard-x86_64.AppImage`, never the Windows installer or its update copy (SHA-256 checked as on Windows); "Restart to update" renames it over the running AppImage (same folder: atomic, the running copy keeps its open file) and a shell starts it once this process is gone (else the single-instance lock sends it back). Only from an AppImage in a writable folder; LD_LIBRARY_PATH as it was before PyInstaller's loader, no AppImage runtime variables | `linux/updates.py` |
| Import from other soundboards | Soundux for Linux's own config (`~/.config/Soundux`, or its Flatpak's), its hotkeys X key codes turned into Windows ones; EXP Soundboard's last board from Java's preferences file; Soundpad and Resanance (and Soundux for Windows) in Wine / Proton prefixes (`$WINEPREFIX`, `~/.wine`, Steam's `compatdata`). A board's Windows paths are found here: `\` turned into `/`, `Z:` is `/`, another drive is that drive in the board's own prefix (else `$WINEPREFIX` / `~/.wine`); a file's name comes out right even when it's missing | `linux/otherboards.py`, `linux/soundux.py`, `linux/expboard.py`, `linux/wine.py` |
| Straight into my mic | the board makes a mic of its own, "Onion Board Mic" (a null sink the engine plays the send mix into + a source remapped from its monitor, both hidden from the app's device lists so nobody picks them as their own mic or speakers), and on the one click makes it the default input: Discord, games and browsers on Default hear your voice and your sounds with nothing to pick; no plug-in, root or restart (see *the design* below). The board keeps recording your real mic by name: WirePlumber 0.5 moves a stream aimed at the default along when the default changes, so the board's mic is opened again once its own mic is the default (it had followed onto it: the board heard itself and the voice was lost). It exists only while the board runs: a quit or another route puts your mic back as the default and takes it away, and a holder shell does the same when the app dies (kill -9, a crash, a logout), even through Ctrl+C sent to the app's group. Checked on Fedora 44 (PipeWire 1.6.2, a stand-in mic fed a tone): a recorder on Default hears the voice and the pads, the board records the real mic, kill -9 and SIGTERM leave the real mic the default with nothing left; on WSLg's PulseAudio the holder's clean-up moved a recorder on Default back to the real mic. The CI AppImage (e5363f3) does the same on Fedora (the frozen app's pactl and holder shell work; kill -9 leaves the real mic the default, nothing left) with 0 underruns and 0 stalls at "low", headless on the cable and with the window on Plasma on the mic route: the 4 drop-outs a from-source run showed were the source run's (Python 3.14), not the status thread. The status is asked on a thread (each pactl stalled the window and, on PulseAudio, every stream). The cable stays as the fallback ("Use the virtual cable instead") and gets the same mix while it exists | `linux/directmic.py`, `linux/engine.py`, `linux/audio.py`, `linux/ui.py` |
| Control API after a restart | upstream turns SO_REUSEADDR off (on Windows it lets two programs share the port); on Linux it only lets a new listener bind while the old connections wait out TIME_WAIT, so a board restarted within a minute of answering a request couldn't listen (Onion Pocket, Stream Deck dead until the next start; found by the Fedora mic test). On here; two boards still can't share the port | `linux/remote.py` |
| Usage count (1.9.0) | as upstream (only a built copy sends, once a day, the version and a random ID; switched off in Settings → Privacy & security), told apart from Windows: the daily count goes to `/app/linux/<version>` (titled "… (Linux)") and events end in `/linux` (`first-start/linux`, `update-now/A-to-B/linux`), so GoatCounter shows Linux under /app/linux/. The Windows installer's "Count me in" box has no AppImage twin, so a Linux copy is counted from its first start unless switched off | `linux/usage.py` wraps `hits()` (hook at `usage.py`'s end); `tests/test_linux_usage.py` |
| Triggers tab | hidden (not removed: everything that looks it up still finds it), and it never nudges. Onion Watch (its own repo) captures the screen with DXGI / GDI; 0.6.5's module zip does install and load here without errors, but only says it works on Windows. Porting it (X11 capture: XShm, XComposite for one window; a portal on Wayland) is its own project, in that repo; then this tab comes back | `linux/ui.py` |
| Overlay | "The one the game is on" follows the X11 window in front (its middle picks the monitor; `overlay.pick_screen` matches it as on Windows). Upstream only asks on Windows, so `linux/ui.py` patches the overlay's screen choice. A Wayland window in front: its chosen screen. *Show preview* lets clicks through while it's up (upstream: a Windows window style; here Qt's `WindowTransparentForInput`, an empty X11 input shape, checked on Xvfb) | `linux/keys.py`, `linux/voicesdk.py`, `linux/ui.py` |
| Voice engine suggestion | *Who's listening* suggests the game in front's voice engine: the X11 active window (`_NET_ACTIVE_WINDOW`, so games under XWayland too) → `_NET_WM_PID` → a Proton / Wine game's .exe from its command line (`Z:\` is `/`, another drive in its `WINEPREFIX`), a native program's `/proc/<pid>/exe`; the scan is upstream's. Desktop and Wine programs (`/usr`, `C:\windows`) don't count. A native libvivoxsdk.so isn't looked for; Wayland windows give nothing | `linux/voicesdk.py`, `linux/x11.py`, `linux/ui.py` |
| "✓ done" labels | a label wider than the one it replaced now gets its room (showed with Linux fonts) | `ui/busy.py` |
| Tests | `tests/test_linux_*.py`; `tests/platform_hooks.py` skips tests of Windows itself (each with its reason) and guards real MIDI / autostart / sound server. Upstream's suite runs on 4 workers (pytest-xdist); each test's Xvfb picks a free display itself (`-displayfd`) and each dbus-daemon has its own address, so workers never share one. The tests never see the desktop's own `DISPLAY` / `WAYLAND_DISPLAY` (`tests/platform_hooks.py`): run from a desktop, the apps tests made grabbed hotkeys on the real X server and their leftover hotkey threads segfaulted later tests | |
| Dependencies | `requirements-linux.txt` = `requirements.txt` + jeepney (kept apart so upstream merges never touch `requirements.txt`) | |
| CI | `.github/workflows/linux.yml`: tests on Ubuntu 24.04 (Xvfb with keymap), the AppImage on 22.04, and on a published release the AppImage attached to it. `checks.yml` runs the Windows tests. Since 1.8.0 it fails about one run in two on upstream's own flaky tests (`test_radio_hitches.py`'s 6 ms timing limit on a shared runner, `test_mapped.py`'s cache race): upstream's main fails the same way; public PRs #17 and #18 change both | |
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
3a. **Drop-outs with the whole app at "low"**: done. Found and fixed on WSLg (not the
   GIL: the unplug check's `pactl list` every 2-3 s stalled every stream at once; see
   *Audio devices*). Fedora 44 with the CI build (a4ecac5), 45 s at "low" with three
   pad presses, headless and the window on Plasma: 0 underruns, 0 stalls, clean
   peaks through the cable (the build before was 0 there too: Fedora's `pipewire`
   device never goes under 40 ms); the `pactl subscribe` watcher is gone after a
   normal quit and after `kill -9`.
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

## Straight into my mic on Linux: the design

Upstream's default since 1.9.0. On Windows it's a capture effect (an APO DLL) on the
real mic: apps keep recording the mic they already use, and the effect swaps in what
the board renders. Linux needs no hook in the mic's own path: the sound server lets
any program make a microphone, and apps on "Default" follow the default.

**What it is.** The board makes a virtual source, **"Onion Board Mic"** (a null sink
the engine plays into + a remap source of its monitor, made like the cable but its
own pair, so the cable stays as it is: the fallback, and apps already set to it keep
working), and makes it the **default input**. Discord, games and browsers left on
"Default" hear it with nothing to pick. Into it goes the whole send mix: the real mic
(after the voice changer, gate and mic volume) plus the sounds, what upstream's
replace mode sends (`MODE_REPLACE`). No plug-in, no root, no restart: `pactl` only,
on PipeWire and PulseAudio alike. Unlike the cable it is only there while the board
runs (no `default.pa` / drop-in entry): a default mic that nothing feeds would mute
the user in every call.

**The board never hears itself.** The engine captures the real mic by its own name,
never "Default": once ours is the default, "Default" is itself (a loop). Before the
switch the default input's name is saved as the user's mic (`cfg.mic_device` when it
is None, "the default mic"); a mic picked by hand stays. The mic meter, mic check and
voice changer keep working on the clean mic, as upstream's ring gives them on Windows.

**Putting the user's mic back.** On quit, on choosing another route, and when the
Settings switch turns it off: the default input goes back to the saved mic, then the
pair is unloaded. Checked on Fedora 44 (PipeWire 1.6.2): with the virtual source the
default and a `parecord` on Default recording it, unloading it moved the recording
to the real mic and the default back to it by themselves (WirePlumber keeps
`default.configured.audio.source` naming ours, so it would become the default again
whenever it reappears: the board sets it back to the user's mic before unloading).
When the board is gone without a quit (a crash, `kill -9`, a power cut):
- modules loaded with `pactl` belong to the sound server and outlive the app, so the
  pair stays, now silent: the user muted. The load goes through a small shell holding
  a pipe from the app (the unplug watcher's trick): when the app's end closes, however
  it died, the shell sets the saved mic back as the default and unloads both modules.
- a power cut or logout kills the shell too, but then the sound server restarts
  without the pair. The next start finds a leftover pair (from a holder that died
  with the session's sound server still up, say) by its name, puts the default back
  first, then makes it again.
- PulseAudio: `module-rescue-streams` (loaded by its default.pa) moves a removed
  source's recordings to the default; to check on WSLg's PulseAudio.

**Upstream's states, on Linux.**

| upstream (`directmic.status`) | Linux |
|---|---|
| missing | never set up (the one click not pressed yet), or switched off |
| ready | set up: made and the default input, or not there yet (it goes with every quit: the engine makes it, and takes the default, as it opens it; if that fails, the engine's error shows with the one-click button) |
| other | there, but another mic is the default (picked in the system's Sound settings, or by another app): one click makes it the default again |
| wiped / outdated | never (nothing takes it off; no DLL version) |
| effect not running (`_direct_not_running`) | never: no effect to fail to load (`installed_on()` is []) |

The Setup tab's and the first-run guide's mic button make it, with no admin prompt
(the "Windows asks for permission once" lines get Linux text: "Onion Board makes a
mic called Onion Board Mic and sets it as the default"); "Use the virtual cable
instead" stays. Apps that pinned a mic by name (Discord's Input Device set to the
headset, OBS's Mic/Aux, a game with its own list): the guide's line "pick **Default**
or **Onion Board Mic** there"; Who's listening can later name an app recording the
real mic directly (PipeWire's `Stream/Input/Audio` nodes, the `listeners` row).

**Delay.** The path is the cable's (engine → null sink → remap source). Measured on
Fedora 44 in the VM (`fedlat.sh`: a click train into a stand-in mic, the real mic and
what the board sends recorded side by side through two identical loopbacks): your
voice arrives 84-94 ms after the real mic through Onion Board Mic, 99-116 ms through
the cable (two runs each; PipeWire's ALSA device never goes under 40 ms each way). No
slower than the cable.

**Settings saved on Windows or by 1.9.1 here.** 1.9.1 moves cable users to the mic
once and writes `"route": "mic"`; this port keeps that value on disk while it runs on
the cable (`linux/library.py`). Once the mic route exists here, those users would be
moved onto it too, as upstream moved its users. Choice 1 below decides whether that's
wanted (changing the system's default input is more visible than Windows' effect).

**Choices for the user** (asked; built this way until answered):
1. As on Windows: new users (and 1.9.1's one-time move off the cable) are on the mic
   route, but the system's default input only changes on the one click ("Put my
   sounds straight into my mic", in the guide and on the Setup tab); until then the
   cable carries everything, as upstream does before its admin prompt.
2. The mic only while the board runs (no muted calls after a quit), not kept at login
   like the cable.

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
proxy's own `slow.test`; the timer now starts once the download is open. A fifth,
from 1.8.0: `test_clipeditor.py`'s fixture waited for the Apps tab's first look at
the running programs by watching the lister's `_busy` flag, but the lister clears it
just before it hands the result over. On a slow runner (this repo's Linux CI, three
runs in a row, 2-4 different tests each time) that late "nothing running" arrived
mid-test and stopped the clip editor's capture or dropped the card. The fixture now
waits for the result itself and stops the tab's 1.5 s re-look (the tests say what's
running); a 2 ms delay put between the two broke 7-11 of its 16 tests, 0 after. A sixth, from 1.9.0: `test_uigc.py`'s
`test_a_cycle_is_never_collected_on_another_thread` expects `collect_due((1, 1, 1))` to
collect generation 2, but with automatic collection off the older generations' counts
only grow when a younger one is collected: after a test that ended on a full
collection (or as the first one, (n, 7, 0) here) they're 0 or 1 and only generation 0
is due, every time (failed one full run in two here). It sets the counts up itself now. A seventh, from 1.9.x (#28's conftest): `closed_port()` put a port number in `_CLOSED_PORTS` for good, and connections to those are refused at once; the system hands the number to later servers too, so now and then a test's own web server was refused (`test_net.py`'s `test_environment_proxies_dont_steer_the_proxy_opener`: "the proxy closed the connection", one full run in seven here). A port stops counting as closed once something listens on it (`tests/test_closed_ports.py`).
Not a test: `MainWindow` starts `load_triggers`' 50 ms timer while `_build_ui` runs,
then the splash's `pump()` runs pending events before `__init__` sets `_shut_down`; on a
slow PC (the Fedora VM, every start with the 1.9.1 AppImage) the timer fired first:
AttributeError, logged as a crash. `linux/ui.py` gives the class a `_shut_down = False`
default; upstream would set it before `_build_ui` (`tests/test_linux_ui.py` reproduces it).

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
