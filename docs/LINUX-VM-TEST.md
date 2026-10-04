# Testing the Linux build in a VM on your Windows PC

A prompt for Claude Code running on the Windows PC (the real desktop). It sets up
the lightest Linux that can run the app (WSL 2 with WSLg: a real Linux kernel,
Wayland + XWayland windows and sound, no VM to manage), then tests the AppImage the
way people will get it, ending with a "call" from the Linux app to the Windows
desktop over localhost through the same Opus codec Discord uses.

What it covers: the AppImage starting, the virtual cable on plain PulseAudio (WSLg)
and on PipeWire, the window and setup guide by eye, the Remote API driving the
Linux app from Windows, and sound arriving at the "other end" after Opus. What it
can't: hotkeys inside a real game, KDE / GNOME's Wayland portal (WSLg's compositor
has none), a real Discord call. For those, a Fedora KDE live ISO in Hyper-V is the
next step (the last section of the prompt).

Copy everything inside the box into Claude Code on the Windows PC:

````text
Test the Linux build of Onion Board (private repo Onion-Alien/onion-board-linux,
branch main) in WSL 2 on this Windows PC, and report what passed and failed.

Ground rules:
- Ask me before anything that needs admin rights or a restart (installing WSL), and
  before opening any window (I may be in a game).
- Don't commit or push from the VM. Write results to a report file, not the repo.
- Nothing personal (user names, paths under C:\Users\<me>, IPs) goes into anything
  you'd later commit.

1. WSL with shared localhost
   - Check `wsl --status` / `wsl -l -v`. If there's no Ubuntu-24.04, ask me, then
     `wsl --install -d Ubuntu-24.04` (may need a restart).
   - Turn on mirrored networking so 127.0.0.1 is the same on both sides: in
     %UserProfile%\.wslconfig put
         [wsl2]
         networkingMode=mirrored
     then `wsl --shutdown` and start Ubuntu again. Check with: in WSL
     `python3 -m http.server 8765` and on Windows `curl http://127.0.0.1:8765`.

2. In WSL (Ubuntu 24.04): tools, the code, the AppImage
   sudo apt update && sudo apt install -y git gh python3-venv pulseaudio-utils \
       pipewire pipewire-pulse wireplumber ffmpeg espeak-ng dbus imagemagick \
       libportaudio2 libsndfile1 libegl1 libgl1 libxkbcommon0 libxkbcommon-x11-0 \
       libfontconfig1 libnss3 libxcomposite1 libxdamage1 libxrandr2 libxtst6 \
       libxkbfile1 libxcb-cursor0 xvfb xkb-data x11-xkb-utils
   gh auth login            # the account that can see the private repo
   gh repo clone Onion-Alien/onion-board-linux ~/obl && cd ~/obl
   python3 -m venv .venv && .venv/bin/pip install -r requirements-linux.txt
   # the AppImage CI built for the newest green "linux" run on main:
   gh run list -R Onion-Alien/onion-board-linux -w linux -b main -s success -L 1
   gh run download <run id> -R Onion-Alien/onion-board-linux \
       -n OnionBoard-x86_64.AppImage -D ~/ob && chmod +x ~/ob/OnionBoard-x86_64.AppImage

3. Headless checks (no windows)
   a. The AppImage starts and loads everything it ships:
      QT_QPA_PLATFORM=offscreen ~/ob/OnionBoard-x86_64.AppImage \
          --appimage-extract-and-run --selftest
      Expect "OK: Onion Board … self-test passed".
   b. The cable on plain PulseAudio (WSLg's sound server):
      .venv/bin/python scripts/linux_audio_check.py --remove      -> expect PASS
   c. The cable on PipeWire (most desktops today), in a private session so WSLg's
      sound isn't touched:
      dbus-run-session -- sh -c 'pipewire & sleep 1; wireplumber & pipewire-pulse &
          sleep 2; env -u PULSE_SERVER .venv/bin/python scripts/linux_audio_check.py --remove'
      -> expect PASS.
   d. The unit tests here too (a third machine):
      .venv/bin/pip install -r requirements-dev.txt pytest-timeout
      QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q --timeout 300

4. The window (ask me first: it opens a window on my desktop)
   - Start it: ~/ob/OnionBoard-x86_64.AppImage --appimage-extract-and-run
   - Go through the setup guide: "Make the virtual cable" should work at once (no
     download, no restart). Note anything still worded for Windows, cut-off text,
     or a button that does nothing. Take screenshots (Win+Shift+S is fine, or
     `import -window root shot.png` from imagemagick in WSL).
   - Add a short sound (any WAV/MP3), play it with its pad, hear it on the PC's
     speakers (WSLg sends WSL's sound to Windows).
   - Settings -> Remote: turn it on. If Onion Board for Windows also runs here,
     give the Linux one port 7475 (mirrored networking shares ports) and note the
     key it shows.

5. The "call": Linux app -> Opus -> Windows desktop, over localhost
   This is what a Discord listener gets: what the app puts into its cable, mono,
   Opus at a voice bitrate, decoded on the other side.
   - Windows: `winget install Gyan.FFmpeg` if ffmpeg isn't there.
   - WSL, send the cable's far end ("Onion Board Cable Output", what a chat app
     would use as its mic) as Opus over RTP to the Windows side:
       ffmpeg -f pulse -i onionboard_cable_out -ac 1 -ar 48000 -c:a libopus \
           -b:a 64k -application voip -f rtp rtp://127.0.0.1:5004 -sdp_file ~/call.sdp
     (pactl list short sources shows the source's real name if it differs.)
     Copy ~/call.sdp to Windows (\\wsl$\Ubuntu-24.04\home\<user>\call.sdp).
   - Windows, record 15 s of what arrives:
       ffmpeg -protocol_whitelist file,udp,rtp -i call.sdp -t 15 heard.wav
   - Meanwhile press the pad from WINDOWS through the Linux app's Remote API (this
     is the localhost link between the two):
       curl "http://127.0.0.1:7474/api/play?name=<your sound>&token=<key>"
     (7475 if you changed it). Also try /api/status and /api/stop.
   - Check heard.wav isn't silent (python: RMS of the samples, or listen with
     ffplay) and that it sounds like the sound, not chopped or robotic. Optional,
     numbers for the codec on its own: `.venv/bin/python scripts/codec_bench.py
     --profiles discord` in WSL.

6. Report
   Write vm-test-report.md next to wherever you ran this (not in the repo): each
   step PASS / FAIL with the command output that shows it, the screenshots, and
   anything that looked wrong. Then tell me the three most important problems.

7. Next, if all of that passes (ask me first; heavier): a real desktop
   Hyper-V (Windows Pro) or VirtualBox, Fedora KDE live ISO (Plasma on Wayland,
   PipeWire, the GlobalShortcuts portal), 4 GB RAM, no install needed. In it: the
   AppImage, the setup guide, hotkeys with a native Wayland window in front (the
   desktop should ask once to allow the shortcuts; check hold-to-play), Discord's
   Linux app with the cable as its mic, and a second Discord account on Windows in
   the same call listening.
````
