<p align="right"><img src="https://visitor-badge.laobi.icu/badge?page_id=Onion-Alien.onion-board" alt="visitors"></p>

# Onion Board for Linux

A free soundboard for Linux. Press a pad or a hotkey, even in-game, and **your
friends in Discord or your game hear the sound**, with your voice or without it.
Or send it to your stream, or keep it to your own headphones.

This is the Linux version of [Onion Board](https://github.com/Onion-Alien/onion-board)
(on Windows? get it there).

## 🐧 Download

**Not released yet.** The first AppImage (`OnionBoard-x86_64.AppImage`, 64-bit PC, any
distribution from Ubuntu 22.04 on) goes up on the [releases page](../../releases) soon.
Until then you can [run it from source](#run-it-from-source).

<!-- release -->
Not released yet · 64-bit Linux (Ubuntu 22.04 or newer, Fedora, …) · free, no account, no
ads, anonymous usage count you can switch off · [what's new](CHANGELOG.md)
<!-- /release -->

![Onion Board's sound pads](docs/screenshots/sounds.png?v=5ee6a92c)

| | |
|---|---|
| ![Voice changer and text-to-speech](docs/screenshots/voice.png?v=cfedced0) | ![Send a program's sound](docs/screenshots/apps.png?v=65ad7857) |
| **Voice**: change your voice live, or type and a computer voice says it | **Apps**: send one program's sound (music, a video) to your friends |
| ![Setup at a glance](docs/screenshots/setup.png?v=97216a35) | |
| **Setup**: one look tells you whether others can hear you | |

## What it does

- **Sounds into Discord and games.** By default they go straight into your mic: one
  click and Onion Board makes **`Onion Board Mic`** your default microphone, so Discord
  and games set to *Default* hear your voice and your sounds. Nothing to install, no
  root. Or use a virtual cable the app makes for you, any other output you pick (a
  mixer, a capture card, OBS), or nowhere, so only you hear them. Your voice goes
  along, or tick it off and send only sounds.
- **Hotkeys that work in-game** (X11, games under XWayland, and KDE Plasma / GNOME 48+
  on Wayland), MIDI pads, an in-game overlay, Stream Deck support, and your pads on
  your phone with the optional Onion Pocket add-on.
- **Add sounds from anywhere**: drag in files, or search YouTube and SoundCloud
  inside the app. Coming from **Soundux**? Your sounds and hotkeys come along.
- **Effects on any sound**: trim, speed, pitch, bass boost, reverse. One-click
  *Ear rape*, *Nightcore*, *Slowed + reverb*.
- **Voice changer, text-to-speech** and live voice-to-speech.
- **Instant replay**: one key turns the last 30 seconds you heard into a pad.
- **World radio**, a **clean stream output for OBS**, and 31 themes.

Not on Linux yet: screen triggers (the Onion Watch add-on is Windows-only for now).
The full list is in [docs/FEATURES.md](docs/FEATURES.md).

## 📱 Your pads on your phone

<img align="right" width="220" src="https://raw.githubusercontent.com/Onion-Alien/onion-pocket/main/docs/screenshots/phone.png" alt="Onion Pocket on a phone: colourful pads by category, two playing, Stop all and the volume, and the Pads, Radio and Sound tabs at the bottom">

With the free **[Onion Pocket](https://github.com/Onion-Alien/onion-pocket)** add-on,
your phone becomes a remote for your board. Scan a QR code on your PC with your
phone's camera, tap a pad, and it plays on the PC, into Discord or your game like
any other pad. Its **Radio** tab runs the radio (your favourites, popular stations,
search, live or just for you) and its **Sound** tab changes the speed, pitch, bass
and effects of what's playing, and who's listening.

- **Nothing to download on your phone.** It opens in the phone's browser, on iPhone
  or Android. No app, no account.
- **One click to get it:** Settings → Remote → **Get Onion Pocket**. It comes
  straight from its GitHub release and is checked before it's installed.
- **Safe by default.** It's off until you switch it on, and only phones on your own
  Wi-Fi can reach it, with their own key from the QR code. *Forget phones* locks
  them all out again.
- **It can't touch your mic.** A phone can play your pads, run the radio, change the
  live speed, pitch and effects, and mute you. Never your mic, the voice changer or
  your files.
- If your firewall (ufw, firewalld) blocks phones, let port 7475 through on your home
  network only. Use it at home rather than on public Wi-Fi.

Optional: if you never get it, nothing changes.

<br clear="right">

## Get started

1. **Download `OnionBoard-x86_64.AppImage`** (once it's out, see [Download](#-download)),
   make it runnable (`chmod +x OnionBoard-x86_64.AppImage`, or *Properties → Allow
   executing* in your file manager) and start it. It updates itself from then on.
2. **Follow Bun the bunny's four steps**: your mic, your headphones, where your
   sounds go, and what to set in Discord or your game.
3. **Pick where your sounds go** (step 3 of Bun's guide, or later on the *Setup* tab →
   Devices → *Send to others through*):
   - **Straight into my mic** (the default): one click makes **`Onion Board Mic`** your
     default microphone. Discord and games set to *Default* hear your voice and your
     sounds; an app set to one particular mic: pick *Default* or `Onion Board Mic`
     there. Your own mic is the default again whenever Onion Board closes. In Discord,
     set *User Settings → Voice & Video → Input Profile* to **Studio** so it doesn't
     filter your sounds out.
   - **The virtual cable** (the other way): *Use the virtual cable instead* makes one
     (nothing to download); in Discord or your game, set your microphone to
     **`Onion Board Cable Output`**.
   - **Another device**: any output but your headphones, such as a mixer, a capture
     card or a second sound card. In OBS add it as an audio output capture.
   - **Nowhere**: only you hear your sounds (and the *Stream output* if you set one).
     Nothing to change in Discord or your game.
4. **Drag sounds onto the window** and double-click a pad to play it. Right-click a
   pad for a hotkey or **Effects…**.

**Hotkeys:** they work on X11 and in games under XWayland. On a Wayland desktop, KDE
Plasma and GNOME 48+ ask you once to allow them; on other Wayland desktops (Sway…) they
only work while an X11 window is in front.

### Something's not right?

- **Friends hear nothing:** the pill at the top should be green. Straight into your
  mic, Discord or the game must be on *Default* (or `Onion Board Mic`). With the cable,
  their microphone must be `Onion Board Cable Output`. With another device, it reads
  *Sending to:* and whatever sits on the other end must be picking that device up.
  With *Nowhere*, only you hear sounds, on purpose.
- **They hear sounds but not you:** tick **Others hear it** under *My mic*.
- **Check it yourself:** *Setup → Record 6s → play back* records what others get (it
  works any way but *Nowhere*).
- **Switch how sounds go out any time:** *Setup → Devices → Send to others through*.
- **Still stuck?** [Open an issue](../../issues/new/choose) and attach
  `~/.local/share/OnionBoard/onionboard.log` (skim it first: it has your device names).

Your sounds and settings live in `~/.local/share/OnionBoard/`.

## Run it from source

Needs Python 3.12 or newer, git, and a few system libraries (most desktops have them
already). On Ubuntu / Debian:

```bash
sudo apt install python3-venv libportaudio2 pulseaudio-utils ffmpeg libxcb-cursor0
```

On Fedora: `sudo dnf install portaudio pulseaudio-utils ffmpeg-free xcb-util-cursor`.
Then:

```bash
git clone https://github.com/Onion-Alien/onion-board-linux.git
cd onion-board-linux
python3 -m venv .venv
.venv/bin/pip install -r requirements-linux.txt
.venv/bin/python main.py
```

`git pull` and the same `pip install` get you the latest.

## Free, and it stays free

[MIT with the Commons Clause](LICENSE): use it anywhere, monetized streams included,
change it and share your version for free. Nobody may sell it; if you paid for
Onion Board, you were ripped off. The name and logo aren't covered, so your own
version needs its own name.

Onion Board comes with no sounds. Only play what you have the right to use. It isn't
affiliated with YouTube, SoundCloud, Myinstants, Discord, Soundux or any other
service it mentions.

### Support Onion Board

**Chip in** (crypto only for now; trust only the addresses on
`github.com/Onion-Alien/onion-board`):

| Coin | Address |
|---|---|
| **Bitcoin** (BTC) | `bc1qrr382vd6xsfavyuqvwxjy5watfd4fqr0tufyk7` |
| **Ethereum** (ETH, USDC…), also Base, Arbitrum, Polygon, Optimism | `0x11C66De40F99628aA52234Ae3aCa550Da5491A32` |

A star or telling a friend helps just as much.

## For developers

Set up as in [Run it from source](#run-it-from-source), then add
`.venv/bin/pip install -r requirements-dev.txt`. Checks: `.venv/bin/ruff check .` and
`.venv/bin/python -m pytest`. `./build-linux.sh` builds the AppImage.

- [docs/LINUX-PORT.md](docs/LINUX-PORT.md): how the port works, and merging upstream
- [docs/LINUX-PROGRESS.md](docs/LINUX-PROGRESS.md): how far it is from launch
- [docs/DEVELOPING.md](docs/DEVELOPING.md) · [docs/CODE.md](docs/CODE.md): the shared
  app (written for Windows)
- [CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md) ·
  [docs/BACKUP-FORMAT.md](docs/BACKUP-FORMAT.md)
