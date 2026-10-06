"""Linux side of soundboard.directmic: "Straight into my mic" without a plug-in.

On Windows it's a capture effect (an APO DLL) put on the real mic with an admin
prompt. Linux needs no hook in the mic's own path: the board makes a microphone of
its own and makes it the default input, so Discord, games and browsers left on
"Default" hear it with nothing to pick (docs/LINUX-PORT.md, *Straight into my mic on
Linux: the design*):

  "Onion Board Mic Input"  a null sink the engine plays the send mix into (hidden from
                           the app's device lists: linux/audio.py)
  "Onion Board Mic"        a source remapped from its monitor: the default input

Into it goes the whole send mix (your mic after the voice changer, plus the sounds),
what upstream's replace mode sends. The board itself keeps capturing the real mic by
name (linux/audio.py: "the default mic" is never this one), so it never hears itself.

It only exists while the board runs: a default mic that nothing feeds would mute the
user in every call. The modules are loaded with pactl (they belong to the sound server
and outlive the app), so a small shell holds a pipe from the app; when the app's end
closes, however it ended (a quit, a crash, kill -9), the shell puts the user's mic
back as the default and unloads both modules. A quit or a change of route does the
same at once (release()).

The upstream states, here (status()):
  missing   never set up (or switched off): one click
  other     there, but another mic is the default (picked in the system's settings):
            one click makes it the default again
  ready     there and the default input, or set up and made as the engine opens it
'wiped' and 'outdated' never happen: nothing takes it off, there's nothing to update.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from soundboard import linux

log = logging.getLogger(__name__)

__all__ = ["AVAILABLE", "SINK", "SOURCE", "SINK_DESC", "SOURCE_DESC", "_status",
           "anything_installed", "capture_endpoints", "cli", "default_source", "endpoint_for",
           "ensure", "exists", "forget_status",
           "install", "installed_on", "is_ours", "registered_dll", "release", "uninstall",
           "user_mic"]

AVAILABLE = True   # the app may offer the mic route
SINK = "onionboard_mic_in"
SOURCE = "onionboard_mic"
SINK_DESC = "Onion Board Mic Input"
SOURCE_DESC = "Onion Board Mic"
RATE = 48000
TIMEOUT_S = 10.0
STATE_NAME = "directmic.json"   # {"on": bool, "user_mic": the user's own source}

# the holder: ignores the signals a terminal or a session sends the app's group, waits
# for the app's end of its stdin to close, then puts things back. $1 the user's mic,
# $2 ours, $3.. the module ids.
HOLD_SH = ('trap "" INT TERM HUP QUIT; cat >/dev/null; '
           'd=$(pactl info 2>/dev/null | sed -n "s/^Default Source: //p"); '
           '[ "$d" = "$2" ] && [ -n "$1" ] && pactl set-default-source "$1"; '
           'shift 2; for m in "$@"; do pactl unload-module "$m" 2>/dev/null; done')

_lock = threading.RLock()
_holder: subprocess.Popen | None = None


# ------------------------------------------------------------------ pactl
def _env() -> dict[str, str]:
    env = linux.pactl_env()
    env["LC_ALL"] = "C"   # parsed: in English whatever the desktop's language
    return env


def _have_pactl() -> bool:
    return linux.pactl() is not None


def _pactl(*args: str) -> subprocess.CompletedProcess | None:
    exe = linux.pactl()
    if exe is None:
        return None
    try:
        return subprocess.run([exe, *args], capture_output=True, text=True,
                              timeout=TIMEOUT_S, env=_env())
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("pactl %s failed: %s", " ".join(args[:2]), e)
        return None


def _short(kind: str) -> list[str]:
    p = _pactl("list", "short", kind)
    if p is None or p.returncode != 0:
        return []
    return [ln.split("\t")[1] for ln in p.stdout.splitlines() if ln.count("\t") >= 1]


def default_source() -> str:
    p = _pactl("info")
    if p is None or p.returncode != 0:
        return ""
    m = re.search(r"^Default Source:\s*(\S+)", p.stdout, re.M)
    return m.group(1) if m else ""


def _props(desc: str) -> str:
    return f"'device.description=\"{desc}\"'"


def exists() -> bool:
    return SINK in _short("sinks") and SOURCE in _short("sources")


def _modules() -> list[str]:
    p = _pactl("list", "short", "modules")
    if p is None or p.returncode != 0:
        return []
    return [parts[0] for parts in (ln.split("\t") for ln in p.stdout.splitlines())
            if len(parts) >= 3 and (f"sink_name={SINK} " in parts[2] + " "
                                    or f"source_name={SOURCE} " in parts[2] + " ")]


def is_ours(pulse_name: str) -> bool:
    """A sound server name that's this mic's (its sink, the sink's monitor, its source)."""
    return pulse_name in (SINK, SOURCE, f"{SINK}.monitor")


# ------------------------------------------------------------------ the state file
def _state_path() -> Path:
    from soundboard.linux import data_home
    return Path(data_home()) / "OnionBoard" / STATE_NAME


def _state() -> dict:
    try:
        d = json.loads(_state_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(**kw):
    d = {**_state(), **kw}
    p = _state_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        log.warning("couldn't save %s", p, exc_info=True)


def user_mic() -> str:
    """The sound server name of the user's own mic (the default before ours), or ""."""
    m = _state().get("user_mic")
    return m if isinstance(m, str) and not is_ours(m) else ""


# ------------------------------------------------------------------ making it
def _load() -> list[str] | None:
    """Load the pair (what of it isn't there). The module ids, None if it failed."""
    if SINK not in _short("sinks"):
        p = _pactl("load-module", "module-null-sink", f"sink_name={SINK}",
                   f"sink_properties={_props(SINK_DESC)}", f"rate={RATE}", "channels=2",
                   "channel_map=front-left,front-right")
        if p is None or p.returncode != 0:
            log.warning("couldn't make the mic's input: %s", p.stderr.strip() if p else "no pactl")
            return None
    if SOURCE not in _short("sources"):
        p = _pactl("load-module", "module-remap-source", f"master={SINK}.monitor",
                   f"source_name={SOURCE}", f"source_properties={_props(SOURCE_DESC)}",
                   "channels=2", "channel_map=front-left,front-right")
        if p is None or p.returncode != 0:
            log.warning("couldn't make the mic: %s", p.stderr.strip() if p else "no pactl")
            return None
    return _modules()


def _hold(mods: list[str]):
    """(Re)start the holder that puts things back when this app is gone."""
    global _holder
    old, _holder = _holder, None
    if old is not None:
        _end_holder(old)
    sh = shutil.which("sh")
    if sh is None or not mods:
        return
    try:
        _holder = subprocess.Popen([sh, "-c", HOLD_SH, "onionboard-mic", user_mic(),
                                    SOURCE, *mods], stdin=subprocess.PIPE,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   env=_env(), start_new_session=True, close_fds=True)
    except OSError:
        log.warning("couldn't start the mic's holder: a crash would leave it the default",
                    exc_info=True)


def _end_holder(p: subprocess.Popen):
    try:
        if p.stdin is not None:
            p.stdin.close()   # its cue: puts things back (already done) and ends
        p.wait(TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        log.debug("the mic's holder didn't end", exc_info=True)


def ensure(take_default: bool = True) -> bool:
    """Make the pair (if it isn't there), hold it, and make it the default input
    (`take_default`), saving the default before it as the user's mic. True if it's
    there afterwards."""
    with _lock:
        cur = default_source()
        if cur and not is_ours(cur):
            _save(user_mic=cur)
        mods = _load()
        if mods is None or not exists():
            return False
        if _holder is None or _holder.poll() is not None:
            _hold(mods)
        if take_default and default_source() != SOURCE:
            p = _pactl("set-default-source", SOURCE)
            if p is None or p.returncode != 0:
                log.warning("couldn't make the mic the default input")
        _look()
        log.info("straight into my mic: %s made; the default input is %s (yours: %s)",
                 SOURCE_DESC, _seen["default"] or "?", user_mic() or "?")
        return True


def release():
    """Put the user's mic back as the default and take the pair away (a quit, another
    route). Nothing if it isn't there."""
    global _holder
    with _lock:
        mods = _modules()
        if mods or _holder is not None:
            mine = user_mic()
            if mine and default_source() == SOURCE:
                _pactl("set-default-source", mine)
            for m in mods:
                _pactl("unload-module", m)
            log.info("straight into my mic: taken away, %s is the default input again",
                     mine or "the system's choice")
        old, _holder = _holder, None
        if old is not None:
            _end_holder(old)
        _seen.update(at=None)


# ------------------------------------------------------------------ upstream's API
def forget_status():
    """Upstream's (its 2 s cache), and what the sound server said last."""
    sys.modules["soundboard.directmic"]._status_cache.clear()
    _seen.update(at=None)


_seen = {"at": None, "busy": False, "there": False, "default": ""}
SEEN_S = 2.0   # how old what the sound server said may be


def _look():
    there = SOURCE in _short("sources")   # (its sink is there whenever it is)
    _seen.update(there=there, default=default_source() if there else "",
                 at=time.monotonic(), busy=False)


def _status(mic_name: str | None) -> str:
    """`mic_name` doesn't matter here: the mic carries whichever one the board records.
    Set up but not there (every start: it goes with each quit) is ready: the engine
    makes it as it opens it; if that fails, the engine's error says so.
    Asked about once a second on the UI thread: the sound server is asked on a thread
    (each pactl stalled the window, and on PulseAudio every stream a little), so the
    answer can be up to SEEN_S old; ensure() and release() update it at once."""
    if not _state().get("on"):
        return "missing"
    if _seen["at"] is None:
        _look()
    elif time.monotonic() - _seen["at"] > SEEN_S and not _seen["busy"]:
        _seen["busy"] = True
        threading.Thread(target=_look, daemon=True, name="directmic-look").start()
    if not _seen["there"]:
        return "ready"
    return "ready" if _seen["default"] == SOURCE else "other"


def install(mic_name: str | None) -> str | None:
    """The one click: make the mic and make it the default. None when done."""
    if not _have_pactl():
        return ("Onion Board needs PipeWire or PulseAudio and their pactl tool (the "
                "pulseaudio-utils package) to make its mic.")
    if not ensure():
        return "Couldn't make Onion Board's mic. The log has the details."
    _save(on=True)
    return None


def uninstall() -> str | None:
    release()
    _save(on=False)
    return None


def anything_installed() -> bool:
    return bool(_state().get("on")) or bool(_modules())


def capture_endpoints() -> list[dict]:
    return []


def endpoint_for(name: str | None) -> str | None:
    return None


def installed_on() -> list[str]:
    # upstream's "the effect never ran on the mic" check (_direct_not_running) asks
    # whether the mic has the effect: there's no effect to fail to run here
    return []


def registered_dll() -> Path | None:
    return None


def cli(args: list[str]) -> int:
    """`--direct-mic remove` (an uninstaller's): take it away, switch it off."""
    if args == ["remove"]:
        uninstall()
        return 0
    return 2
