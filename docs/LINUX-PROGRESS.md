# Linux port: how complete it is

One number for "how far is the Linux port from launch", worked out the same way
every time so it moves at a steady pace instead of by feel.

Each row below is one piece of work, weighted by how big it is (1 = small check,
6 = a whole subsystem). Status is `done` (full weight), `half` (started, works in
part, or works but not yet checked where it matters) or `open` (nothing). The
estimate is the weighted share that's done:

```
python scripts/linux_progress.py              # prints the estimate and what's left
python scripts/linux_progress.py --log "what changed"   # also adds a History line
```

**After every finished task**: change the status of the row(s) it moved (add a row
if the task found new work, with an honest weight), run the script with `--log`,
and put the new number in the commit message or report as "Estimate: N% (was M%)".
Don't raise a weight on something already done or drop one that's left to make
the number move: new work found means the number can go down, and that's fine.

## Items

| Id | Item | Weight | Status |
|---|---|---|---|
| hotkeys-x11 | Global hotkeys on X11 / XWayland (grabs, key-up, hold-to-play) | 4 | done |
| hotkeys-kde | Wayland hotkeys via the portal on KDE Plasma | 3 | done |
| hotkeys-gnome | Wayland hotkeys via the portal on GNOME 48+ | 2 | open |
| hotkeys-other | Wayland with no GlobalShortcuts portal (Sway / wlroots, GNOME before 48): a clear message on what to do, and Hyprland's portal checked | 2 | open |
| audio-core | Audio devices and streams on PipeWire and PulseAudio (pulse / pipewire device, unplug watchdog) | 6 | done |
| audio-fedora | Stock Fedora sound (no "pulse" device, 40 ms floor) | 2 | done |
| dropouts | No drop-outs at "low" with the whole app running | 4 | half |
| cable | Virtual cable made by the app (pactl, made at every login) | 3 | done |
| cable-guide | Setup guide's "Make the virtual cable" clicked through on Fedora | 1 | open |
| setup-guide | Setup guide and every page checked on a real desktop | 2 | half |
| apps-tab | Apps tab and instant replay (PipeWire) | 2 | done |
| midi | MIDI pads (ALSA raw MIDI) | 1 | done |
| autostart | Start at login (XDG autostart) | 1 | done |
| single-copy | One copy at a time (flock lock) | 1 | done |
| data-trash | Data folder and removed sounds to the Trash | 1 | done |
| net-tor | Proxy relay and Tor | 2 | done |
| tts | Text-to-speech (eSpeak NG) and the Voice tab's languages | 2 | done |
| voice-fedora | Voice tab on Fedora (Female voice, Hear my voice, delay label) | 1 | open |
| custom-voices | Custom voices (Piper for Linux) | 1 | done |
| addons | Add-ons (live voice environment, notices) | 2 | done |
| ai-voices | AI voices add-on installed and run on a real Linux desktop | 1 | open |
| import | Import from other soundboards (Soundux, EXP, Wine prefixes) | 1 | done |
| overlay-x11 | Overlay screen choice and preview click-through on X11 | 1 | done |
| overlay-wayland | Overlay preview click-through on native Wayland | 1 | open |
| voice-suggest | Voice engine suggestion from the window in front | 1 | done |
| listeners | Who's listening: the program recording the cable (PipeWire) | 2 | open |
| wording | No Windows wording on screen (table + test) | 2 | done |
| packaging | AppImage build (own PortAudio, prune, licences, self-test) | 6 | done |
| ci-appimage-fedora | Newest CI AppImage tested on Fedora (cable test, hotkeys) | 1 | done |
| certs | HTTPS in a built copy on every distro (Fedora's certificates) | 1 | done |
| self-update | Self-update from an AppImage | 2 | done |
| real-release | A real release: AppImage attached, link works, update from it | 2 | open |
| tests | Upstream suite + Linux tests green on Linux, 4 workers | 4 | done |
| ci | CI: Linux and Windows workflows green | 2 | done |
| ci-win-abort | Windows CI native abort in test_radio (cause found) | 1 | open |
| pocket | Onion Pocket installs and works on Linux | 1 | half |
| discord | A real Discord call: Linux app's cable → Windows listener | 3 | open |
| usb-headset | Real USB headset unplugged / replugged on PipeWire | 2 | open |
| distros | Checked on more than one real distro (Ubuntu desktop, Arch) | 2 | half |
| upstream-merge | Upstream releases merged and kept current | 1 | done |
| launch | Merged back into the public repo, Linux download live | 3 | open |

## After launch (not counted)

What other Linux soundboards showed us (checked 2026-10-05). These don't block the
launch, so they aren't in the estimate; move one up into *Items* when it's picked up.

- **Where the others stand.** Soundux, the old favourite, is unmaintained (last
  release 2021). The active ones (PipeWire Soundpad, Linux-SoundBoard, OpenWire,
  HonkHonk, Noisitron) each do part of the job: a PipeWire virtual mic and
  hotkeys, plus one of trim, effects or a MyInstants search. None has YouTube
  import, trim, effects, a voice changer and a phone remote together, and none has
  a phone remote at all. The pitch: *the Soundux replacement that does it all*.
- **Flathub, then AUR.** Every maintained Linux soundboard ships a Flatpak, most an
  AUR package too; AppImage-only is harder to find. Flathub needs PipeWire / Pulse
  socket access, the portal for hotkeys, and `pactl` reachable from the sandbox for
  the cable (or the cable made another way).
- **Hotkeys without the portal.** The others fall back to evdev (PipeWire Soundpad:
  reads `/dev/input`, needs the `input` group) or swhkd (Linux-SoundBoard: a heavy
  install). If we add one, keep it opt-in with the group step explained in words.
- **Import from today's boards.** People coming from PipeWire Soundpad or
  Linux-SoundBoard (SQLite library), next to the Soundux import we already have.
- **Onion Pocket on Linux** is the one thing no Linux soundboard has; worth
  finishing the `pocket` row and saying so in the launch post.
- **Loudness per sound.** Linux-SoundBoard evens out sounds by loudness (LUFS) when
  they're added; an upstream idea, not Linux-only.
- **Tray on GNOME** needs the AppIndicator extension; say so if the tray matters
  for closing to tray.

## History

| Date | Estimate | Change |
|---|---|---|
| 2026-10-05 | 80% | last gut rating, before this scorecard |
| 2026-10-05 | 68% | scorecard starts: counts launch, a real release, Discord, GNOME the old rating didn't |
| 2026-10-05 | 69% | CI AppImage passes on Fedora (cable, hold-to-play); found + fixed HTTPS on Fedora (half until the next CI build is checked) |
| 2026-10-05 | 68% | merged upstream 1.8.0 (AI voices, clip editor); add-ons need Python 3.12; new row: AI voices on a real desktop |
| 2026-10-05 | 66% | new row from looking at other Linux soundboards: hotkeys on Wayland desktops with no portal; after-launch ideas listed |
| 2026-10-05 | 67% | HTTPS fix confirmed with the CI AppImage on Fedora 44 (update check works with no setting) |
| 2026-10-05 | 69% | drop-outs at low: cause found (the unplug poll's pactl list stalled every stream every 2-3 s), fixed + measured on WSLg (30 -> 4 underruns); Fedora check left |
