"""The virtual cable on Linux, made by Onion Board itself: no driver, no root, no
restart. It is VB-Cable's shape, so everything that already knows "a cable"
(engine.is_virtual, virtual_mic_for, the setup guide, the Discord help) works as is:

  "Onion Board Cable Input"   a playback device (sink): the app sends into it
  "Onion Board Cable Output"  a recording device (source): Discord / games use it as mic

Two ways to have it, both per user:

  create()   now, through the sound server (`pactl load-module`, which PipeWire's
             pipewire-pulse and PulseAudio both take): a null sink plus a source
             remapped from its monitor. Gone when the sound server restarts.
  install()  for good: a PipeWire drop-in (~/.config/pipewire/pipewire.conf.d) that
             makes the same pair, a loopback, every time PipeWire starts; on plain
             PulseAudio, the two load-module lines in ~/.config/pulse/default.pa.
             Also create()s it now, so nothing needs restarting.

remove() takes both away again (Settings, and the uninstall).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from soundboard.linux import config_home

log = logging.getLogger(__name__)

SINK = "onionboard_cable"
SOURCE = "onionboard_cable_out"
SINK_DESC = "Onion Board Cable Input"
SOURCE_DESC = "Onion Board Cable Output"
RATE = 48000
TIMEOUT_S = 10.0
CONF_NAME = "onionboard-cable.conf"
PA_MARK = "# Onion Board virtual cable"


def _pactl(*args: str) -> subprocess.CompletedProcess | None:
    exe = shutil.which("pactl")
    if exe is None:
        return None
    try:
        return subprocess.run([exe, *args], capture_output=True, text=True,
                              timeout=TIMEOUT_S, env=_c_env())
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("pactl %s failed: %s", " ".join(args[:2]), e)
        return None


def _c_env() -> dict[str, str]:
    """pactl's output in English whatever the desktop's language (it's parsed)."""
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    return env


def server() -> str:
    """'pipewire', 'pulseaudio' or '' (no sound server pactl can reach)."""
    p = _pactl("info")
    if p is None or p.returncode != 0:
        return ""
    m = re.search(r"^Server Name:\s*(.+)$", p.stdout, re.M)
    name = (m.group(1) if m else "").lower()
    return "pipewire" if "pipewire" in name else "pulseaudio" if name else ""


def _short(kind: str) -> list[str]:
    """Names from `pactl list short sinks|sources`."""
    p = _pactl("list", "short", kind)
    if p is None or p.returncode != 0:
        return []
    return [line.split("\t")[1] for line in p.stdout.splitlines() if line.count("\t") >= 1]


def exists() -> bool:
    """Both ends are there right now."""
    return SINK in _short("sinks") and SOURCE in _short("sources")


def _props(desc: str) -> str:
    # pactl takes a proplist; the description needs its spaces quoted
    return f'device.description="{desc}"'


def create() -> bool:
    """Make the cable in the running sound server if it isn't there. True if it is
    there afterwards."""
    if exists():
        return True
    if SINK not in _short("sinks"):
        p = _pactl("load-module", "module-null-sink", f"sink_name={SINK}",
                   f"sink_properties={_props(SINK_DESC)}", f"rate={RATE}", "channels=2",
                   "channel_map=front-left,front-right")
        if p is None or p.returncode != 0:
            log.warning("couldn't make the cable's playback end: %s",
                        (p.stderr.strip() if p else "no pactl"))
            return False
    if SOURCE not in _short("sources"):
        p = _pactl("load-module", "module-remap-source", f"master={SINK}.monitor",
                   f"source_name={SOURCE}", f"source_properties={_props(SOURCE_DESC)}",
                   "channels=2", "channel_map=front-left,front-right")
        if p is None or p.returncode != 0:
            log.warning("couldn't make the cable's recording end: %s",
                        (p.stderr.strip() if p else "no pactl"))
            return False
    ok = exists()
    log.info("virtual cable %s", "made" if ok else "still missing after making it")
    return ok


def _our_modules() -> list[str]:
    """Module ids of the null sink / remap source we loaded."""
    p = _pactl("list", "short", "modules")
    if p is None or p.returncode != 0:
        return []
    ids = []
    for line in p.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and (f"sink_name={SINK}" in parts[2]
                                or f"source_name={SOURCE}" in parts[2]):
            ids.append(parts[0])
    return ids


# ------------------------------------------------------------------ for good
def pipewire_conf() -> Path:
    return Path(config_home()) / "pipewire" / "pipewire.conf.d" / CONF_NAME


def pulse_default_pa() -> Path:
    return Path(config_home()) / "pulse" / "default.pa"


def pipewire_conf_text() -> str:
    return f"""# {PA_MARK[2:]}: made by Onion Board (Settings can remove it again).
# Audio played into "{SINK_DESC}" comes out of "{SOURCE_DESC}",
# which Discord and games use as their microphone.
context.modules = [
    {{ name = libpipewire-module-loopback
        args = {{
            node.description = "Onion Board Cable"
            audio.position = [ FL FR ]
            capture.props = {{
                node.name = "{SINK}"
                node.description = "{SINK_DESC}"
                media.class = "Audio/Sink"
                audio.rate = {RATE}
            }}
            playback.props = {{
                node.name = "{SOURCE}"
                node.description = "{SOURCE_DESC}"
                media.class = "Audio/Source"
                audio.rate = {RATE}
            }}
        }}
    }}
]
"""


def pulse_lines() -> list[str]:
    return [
        PA_MARK,
        f"load-module module-null-sink sink_name={SINK} "
        f"sink_properties=device.description=\"{SINK_DESC.replace(' ', '\\ ')}\" "
        f"rate={RATE} channels=2",
        f"load-module module-remap-source master={SINK}.monitor source_name={SOURCE} "
        f"source_properties=device.description=\"{SOURCE_DESC.replace(' ', '\\ ')}\"",
    ]


def installed() -> bool:
    """Set to come back by itself at every login."""
    if pipewire_conf().is_file():
        return True
    try:
        return PA_MARK in pulse_default_pa().read_text(encoding="utf-8")
    except OSError:
        return False


def install() -> bool:
    """Make it now and at every login. True if it's there now."""
    kind = server()
    try:
        if kind == "pipewire":
            p = pipewire_conf()
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(pipewire_conf_text(), encoding="utf-8")
            tmp.replace(p)
        elif kind == "pulseaudio":
            p = pulse_default_pa()
            try:
                text = p.read_text(encoding="utf-8")
            except FileNotFoundError:
                text = ".include /etc/pulse/default.pa\n"   # keep the system's setup
            if PA_MARK not in text:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text.rstrip("\n") + "\n\n" + "\n".join(pulse_lines()) + "\n",
                             encoding="utf-8")
        else:
            log.warning("no PipeWire or PulseAudio found: can't make the virtual cable")
            return False
    except OSError:
        log.warning("couldn't save the virtual cable's settings", exc_info=True)
    return create()


def remove() -> bool:
    """Take the cable away: now and at login. True if it's gone."""
    try:
        pipewire_conf().unlink(missing_ok=True)
    except OSError:
        log.warning("couldn't remove %s", pipewire_conf(), exc_info=True)
    try:
        p = pulse_default_pa()
        text = p.read_text(encoding="utf-8")
        if PA_MARK in text:
            keep = [ln for ln in text.splitlines()
                    if ln != PA_MARK and f"sink_name={SINK}" not in ln
                    and f"source_name={SOURCE}" not in ln]
            p.write_text("\n".join(keep).rstrip("\n") + "\n", encoding="utf-8")
    except FileNotFoundError:
        pass
    except OSError:
        log.warning("couldn't edit default.pa", exc_info=True)
    for mid in reversed(_our_modules()):
        _pactl("unload-module", mid)
    # the PipeWire loopback (made at login from the drop-in) isn't a pactl module: it
    # goes when PipeWire next starts; until then it does no harm
    return not _our_modules()
