"""Audio devices on Linux: every PipeWire / PulseAudio device by its own name.

PortAudio (as the sounddevice wheel loads it) only lists ALSA's "pulse",
"pipewire" and "default" on a desktop, not the devices behind them, while the
engine opens up to four streams on devices the user picked. So:

  the lists     come from the sound server (`pactl list sinks / sources`): each
                device's description ("Headphones", "Onion Board Cable Input"),
                rate and channels, under a stand-in index from FIRST_INDEX up
  a stream      on a stand-in index is PortAudio's "pulse" device, with PULSE_SINK
                (PULSE_SOURCE for a mic) naming the device just while it opens:
                the pulse ALSA plugin reads it then, so each stream goes to its own
                device, one process, no extra libraries. Works on PulseAudio and on
                PipeWire (pipewire-pulse). Where there's no "pulse" device (Fedora
                doesn't install that plugin), PipeWire's own "pipewire" device,
                aimed the same way with PIPEWIRE_NODE.
  unplugged     the sound server moves a stream whose device goes away onto its
                default device and the stream plays on there: no error, no stall
                for the engine's watchdog to see. DeviceWatch keeps one `pactl
                subscribe` open and counts the sound server's "a device came / went"
                events; linux/engine.py then asks whether each stream's device is
                still there (present()), and closes the stream if not; the watchdog
                reopens it once the device is back (a device that isn't there is
                never opened). Asking every few seconds instead stalled every stream
                for ~20 ms each time on PulseAudio (WSLg's: ALSA underruns at "low").

`sd` (a SoundDevice) stands in for the sounddevice module in engine.py and
mainwindow.py (their Linux hooks put it there): it takes the stand-in indices;
real PortAudio indices pass through untouched. engine.py's hook also takes the
device-list functions from here.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass

log = logging.getLogger(__name__)

FIRST_INDEX = 100_000      # stand-in indices: far above any real PortAudio index
TIMEOUT_S = 5.0
PULSE, PIPEWIRE = "pulse", "pipewire"   # PortAudio's ALSA devices to the sound server
PCMS = (PULSE, PIPEWIRE)   # ...the first one there is used
NULL_SINK_LATENCY = 0.1    # the least buffering a PulseAudio null sink plays steadily at
PIPEWIRE_LATENCY = 0.04    # ...and PipeWire's own ALSA device (two of its quanta)


@dataclass
class Device:
    index: int
    kind: str              # "output" | "input"
    pulse: str             # the sound server's name for it (alsa_output.pci-…)
    name: str              # what the lists show (its description)
    rate: int
    channels: int
    null_sink: bool = False   # PulseAudio's module-null-sink (the cable, there)


_lock = threading.Lock()          # one stream opens at a time: the env var is global
_devices: list[Device] | None = None
_defaults: dict[str, str] = {}


def _pactl(*args: str) -> str:
    exe = shutil.which("pactl")
    if exe is None:
        return ""
    env = dict(os.environ)
    env["LC_ALL"] = "C"   # parsed: English whatever the desktop's language
    try:
        p = subprocess.run([exe, *args], capture_output=True, text=True, timeout=TIMEOUT_S,
                           env=env, errors="replace")
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("pactl %s failed: %s", " ".join(args), e)
        return ""
    return p.stdout if p.returncode == 0 else ""


_SPEC = re.compile(r"(\d+)ch (\d+)Hz")


def parse_list(text: str) -> list[dict]:
    """`pactl list sinks|sources` (LC_ALL=C) -> [{name, description, rate, channels,
    monitor_of, driver}]."""
    out: list[dict] = []
    cur: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if raw.startswith(("Sink #", "Source #")):
            cur = {"name": "", "description": "", "rate": 48000, "channels": 2,
                   "monitor_of": "", "driver": ""}
            out.append(cur)
        elif cur is None:
            continue
        elif line.startswith("Name:"):
            cur["name"] = line[5:].strip()
        elif line.startswith("Driver:"):
            cur["driver"] = line[7:].strip()
        elif line.startswith("Description:"):
            cur["description"] = line[12:].strip()
        elif line.startswith("Sample Specification:"):
            m = _SPEC.search(line)
            if m:
                cur["channels"], cur["rate"] = int(m[1]), int(m[2])
        elif line.startswith("Monitor of Sink:"):
            v = line[16:].strip()
            cur["monitor_of"] = "" if v in ("n/a", "") else v
    return [d for d in out if d["name"]]


def refresh() -> list[Device]:
    """Read the sound server's devices again."""
    global _devices
    found: list[Device] = []
    seen: dict[str, int] = {}
    for kind, what in (("output", "sinks"), ("input", "sources")):
        for d in parse_list(_pactl("list", what)):
            if kind == "input" and (d["monitor_of"] or d["name"].endswith(".monitor")):
                continue   # "Monitor of …": what an output plays, not a mic
            label = d["description"] or d["name"]
            key = f"{kind}:{label}"
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                label = f"{label} ({seen[key]})"
            found.append(Device(FIRST_INDEX + len(found), kind, d["name"], label,
                                d["rate"], d["channels"],
                                null_sink=d["driver"] == "module-null-sink.c"))
    info = _pactl("info")
    for kind, field in (("output", "Default Sink:"), ("input", "Default Source:")):
        m = re.search(rf"^{field}\s*(.+)$", info, re.M)
        _defaults[kind] = m.group(1).strip() if m else ""
    with _lock:
        _devices = found
    return found


def present() -> set[str] | None:
    """The sound server's device names now (sinks and sources); None if it can't be
    asked. A device that's gone isn't in the lists the app read earlier: this asks."""
    names: set[str] = set()
    answered = False
    for what in ("sinks", "sources"):
        text = _pactl("list", what)
        answered = answered or bool(text)
        names |= {d["name"] for d in parse_list(text)}
    return names if answered else None


# `pactl subscribe` lines for a device coming or going (not its streams: those are
# "sink-input" / "source-output", and "change" is a volume or a port)
_DEVICE_EVENT = re.compile(r"^Event '(?:new|remove)' on (?:sink|source) #\d+\s*$")


# pactl subscribe only notices the app is gone when it next writes, which may be never:
# a shell holds it and ends it once the app's end of its stdin closes (a crash too)
_WATCH_SH = 'pactl subscribe </dev/null & p=$!; cat >/dev/null; kill $p 2>/dev/null'


def _watch_cmd() -> list[str] | None:
    sh = shutil.which("sh")
    return [sh, "-c", _WATCH_SH] if sh and shutil.which("pactl") else None


class DeviceWatch:
    """One `pactl subscribe` for the app's life: `generation` goes up each time a
    sink or source comes or goes. `alive` is False when there's none (no pactl, the
    sound server restarted): then the caller polls instead, and start() may try
    again later."""

    def __init__(self):
        self.generation = 0
        self.alive = False
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        with self._lock:
            if self.alive:
                return True
            cmd = _watch_cmd()
            if cmd is None:
                return False
            env = dict(os.environ)
            env["LC_ALL"] = "C"
            try:
                self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                              stderr=subprocess.DEVNULL,
                                              stdin=subprocess.PIPE, text=True,
                                              errors="replace", env=env)
            except OSError as e:
                log.warning("pactl subscribe failed: %s", e)
                return False
            self.alive = True
            self.generation += 1   # anything may have changed while nobody watched
            threading.Thread(target=self._read, args=(self._proc,), daemon=True,
                             name="audio-watch").start()
            return True

    def _read(self, proc: subprocess.Popen):
        try:
            for line in proc.stdout:
                if _DEVICE_EVENT.match(line):
                    self.generation += 1
        except (OSError, ValueError):
            pass
        finally:
            with self._lock:
                if self._proc is proc:
                    self.alive = False
                    self._proc = None
                    log.info("pactl subscribe ended: polling for unplugged devices")

    def stop(self):
        with self._lock:
            proc, self._proc, self.alive = self._proc, None, False
        if proc is not None and proc.poll() is None:
            try:
                proc.stdin.close()   # the shell ends pactl, then itself
                proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()


watch = DeviceWatch()


def devices() -> list[Device]:
    if _devices is None:
        refresh()
    return list(_devices or [])


def by_index(index) -> Device | None:
    if not isinstance(index, int) or index < FIRST_INDEX:
        return None
    for d in devices():
        if d.index == index:
            return d
    return None


# ------------------------------------------------------------------ engine's API
def list_devices(kind: str) -> list[dict]:
    """The sound server's devices of kind 'input' or 'output' as [{index, name}]."""
    return [{"index": d.index, "name": d.name} for d in devices() if d.kind == kind]


def default_device_name(kind: str) -> str | None:
    devs = devices()
    want = _defaults.get(kind, "")
    for d in devs:
        if d.kind == kind and d.pulse == want:
            return d.name
    return None


def bluetooth_mic(name: str | None) -> bool:
    """`name` is a Bluetooth headset's mic (bluez_input.… on PipeWire, bluez_source.…
    on PulseAudio): opening it switches the headset to its call profile, as Windows'
    "Hands-Free" mic does."""
    return any(d.kind == "input" and d.name == name
               and d.pulse.startswith(("bluez_input.", "bluez_source.")) for d in devices())


def list_name(index: int) -> str:
    d = by_index(index)
    if d is not None:
        return d.name
    import sounddevice
    return sounddevice.query_devices(index)["name"]


# ------------------------------------------------------------------ sounddevice
def _pcm() -> tuple[int, str]:
    """PortAudio's index of the ALSA device that goes through the sound server, and
    which one it is: "pulse" if it's there, else PipeWire's own "pipewire" (Fedora
    ships only that one: its alsa-plugins-pulseaudio isn't installed by default)."""
    import sounddevice
    return _choose([d["name"] for d in sounddevice.query_devices()])


def _choose(names: list[str]) -> tuple[int, str]:
    for pcm in PCMS:
        if pcm in names:
            return names.index(pcm), pcm
    raise RuntimeError("PortAudio has no 'pulse' or 'pipewire' device: is PipeWire or "
                       "PulseAudio running, with its ALSA plugin installed (pipewire-alsa "
                       "or alsa-plugins-pulseaudio)?")


def _aim(pcm: str, kind: str, dev: Device) -> dict[str, str]:
    """The environment that points a stream opened on `pcm` at `dev`, read by the ALSA
    plugin as it opens, and names it "Onion Board" in volume mixers (else "ALSA
    plug-in [python3]")."""
    if pcm == PIPEWIRE:
        return {"PIPEWIRE_NODE": dev.pulse,   # the sink / source's node.name
                "PIPEWIRE_ALSA": "{ application.name = \"Onion Board\" "
                                 "application.icon_name = onionboard }"}
    # the pulse plugin sets its own name, which only the OVERRIDE variant beats
    return {"PULSE_SINK" if kind == "output" else "PULSE_SOURCE": dev.pulse,
            "PULSE_PROP_OVERRIDE": "application.name='Onion Board' "
                                   "application.icon_name=onionboard"}


def _info(d: Device) -> dict:
    return {"name": d.name, "index": d.index, "hostapi": -1,
            "max_input_channels": d.channels if d.kind == "input" else 0,
            "max_output_channels": d.channels if d.kind == "output" else 0,
            "default_samplerate": float(d.rate),
            "default_low_output_latency": 0.01, "default_low_input_latency": 0.01,
            "default_high_output_latency": 0.1, "default_high_input_latency": 0.1}


def _below(lat, least: float) -> bool:
    """A stream's latency ("low", "high", seconds or None for low) is under `least`."""
    return lat in (None, "low") or (isinstance(lat, (int, float)) and lat < least)


def _open(kind: str, cls, kwargs: dict):
    dev = by_index(kwargs.get("device"))
    if dev is None:
        return cls(**kwargs)
    # a device that's gone (unplugged since the lists were read) mustn't be opened:
    # the sound server would put the stream on its default device instead, sounds
    # meant for the cable on the speakers
    now = present()
    if now is not None and dev.pulse not in now:
        raise RuntimeError(f"device not found: {dev.name}")
    # PulseAudio's null sink (the cable there) stops asking for sound for about 2 s
    # after every underrun (and when a stream starts: linux/engine.py's START_S), and
    # at "low" buffering a busy moment underruns it every few seconds: a cable that
    # carries sound in 2 s bursts. "high" (Safer, 0.1 s) keeps it flowing. Sound
    # cards and PipeWire's sinks don't do this and keep the user's choice.
    lat = kwargs.get("latency")
    if dev.null_sink and _below(lat, NULL_SINK_LATENCY):
        kwargs = {**kwargs, "latency": "high"}
        # the engine's "opened … (latency low)" line names what it asked for
        log.info("%s is a PulseAudio null sink: opened at latency high, not %s",
                 dev.name, lat)
    with _lock:
        index, pcm = _pcm()
        # PipeWire's own ALSA device feeds the graph a quantum (about 21 ms) at a time:
        # a buffer under two of them runs dry over and over (on Fedora 44 "low", 8.7 ms,
        # stalled the cable and dropped out hundreds of times in 10 s; 40 ms none)
        if pcm == PIPEWIRE and _below(kwargs.get("latency"), PIPEWIRE_LATENCY):
            log.info("%s through PipeWire's ALSA device: opened at %d ms, not %s", dev.name,
                     PIPEWIRE_LATENCY * 1000, kwargs.get("latency"))
            kwargs = {**kwargs, "latency": PIPEWIRE_LATENCY}
        env = _aim(pcm, kind, dev)
        old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            return cls(**{**kwargs, "device": index})
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class SoundDevice:
    """Stands in for the sounddevice module where the app opens streams (engine.sd,
    mainwindow.sd): the stand-in indices go through the sound server, everything else
    straight to sounddevice, looked up at each call (so a test's stub stream class is
    still the one used)."""

    def __getattr__(self, name):
        import sounddevice
        return getattr(sounddevice, name)

    def query_devices(self, device=None, kind=None):
        import sounddevice
        d = by_index(device)
        if d is not None:
            return _info(d)
        return sounddevice.query_devices(device, kind) if kind else \
            sounddevice.query_devices(device)

    def OutputStream(self, **kwargs):  # noqa: N802 - sounddevice's name
        import sounddevice
        return _open("output", sounddevice.OutputStream, kwargs)

    def InputStream(self, **kwargs):  # noqa: N802
        import sounddevice
        return _open("input", sounddevice.InputStream, kwargs)


sd = SoundDevice()
