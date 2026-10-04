"""Linux side of soundboard.engine: the device lists are the sound server's
(soundboard.linux.audio), and streams on them open through PortAudio's "pulse"
device (`sd` here replaces the engine's sounddevice). find_device, virtual_outputs
and virtual_mic_for are built on list_devices, so they need no Linux version."""
from __future__ import annotations

import logging
import sys
import threading
import time

from soundboard.linux import audio

log = logging.getLogger(__name__)

__all__ = ["sd", "list_devices", "default_device_name", "list_name", "rescan"]

sd = audio.sd
list_devices = audio.list_devices
default_device_name = audio.default_device_name
list_name = audio.list_name


def rescan() -> bool:
    """Re-read the sound server's devices (one was plugged in) and restart PortAudio,
    as the Windows version does. Kills open streams: reopen after."""
    import sounddevice
    audio.refresh()
    try:
        sounddevice._terminate()
        sounddevice._initialize()
        return True
    except Exception:  # noqa: BLE001
        log.exception("device rescan failed")
        try:
            sounddevice._initialize()
        except Exception:  # noqa: BLE001
            pass
        return False


# ------------------------------------------------------------------ unplugged devices
GONE_POLL_S = 2.0   # how often the sound server is asked which devices are still there
_STREAMS = (("main", "main_stream", "output"), ("mon", "mon_stream", "output"),
            ("obs", "obs_stream", "output"), ("mic", "mic_stream", "input"))


def _device(name: str, kind: str) -> audio.Device | None:
    return next((d for d in audio.devices() if d.name == name and d.kind == kind), None)


# PulseAudio gives a new stream on a null sink (the virtual cable is one) a few
# callbacks, then none for 1.6-2 s before it runs (PulseAudio 17, WSLg's and a
# plain one alike; PipeWire and sound cards start at once). The watchdog's STALL_S
# (1.5 s) took that for a dead stream and reopened it, which started the wait over:
# the cable never carried a sound. A stream gets this long from its opening first.
START_S = 3.0
_SETTERS = (("main", "set_main_device"), ("mon", "set_mon_device"),
            ("mic", "set_mic_device"), ("obs", "set_obs_device"))


def patch_engine(cls):
    """check_streams (the watchdog, about once a second on the UI thread) also closes a
    stream whose device has gone from the sound server, saying so as Windows does
    ("device not found"); the watchdog's retry reopens it there once it's back. The
    sound server is asked on a thread, at most every GONE_POLL_S. And a stream opened
    less than START_S ago isn't stalled yet."""
    orig = cls.check_streams

    for key, setter in _SETTERS:
        def opened(self, *a, _set=getattr(cls, setter), _key=key, **k):
            self.__dict__.setdefault("_opened_at", {})[_key] = time.monotonic()
            return _set(self, *a, **k)
        setattr(cls, setter, opened)

    def check_streams(self):
        now = time.monotonic()
        for key, at in self.__dict__.get("_opened_at", {}).items():
            if now - at < START_S:   # starting: the callbacks' own times can only be newer
                self._last_cb[key] = max(self._last_cb[key], now)
        touched = orig(self)
        st = self.__dict__.setdefault("_gone_poll", {"next": 0.0, "busy": False,
                                                     "present": None, "at": 0.0})
        now = time.monotonic()
        found, st["present"] = st["present"], None
        if found is not None:
            from soundboard import errors
            for key, attr, kind in _STREAMS:
                name = self.names.get(key)
                dev = _device(name, kind) if name and getattr(self, attr) is not None \
                    else None
                # (a stream opened since the server was asked is newer than its answer)
                if dev is not None and dev.pulse not in found \
                        and self._last_try[key] <= st["at"]:
                    log.warning("%s device was unplugged: %s", key, name)
                    self._close(attr)
                    self.errors[key] = errors.plain(RuntimeError(f"device not found: {name}"))
                    self._last_try[key] = now
                    touched.append(key)
        if not st["busy"] and now >= st["next"] and any(
                getattr(self, attr) is not None for _k, attr, _kind in _STREAMS):
            st["busy"], st["next"], st["at"] = True, now + GONE_POLL_S, now

            def ask():
                try:
                    st["present"] = audio.present()
                finally:
                    st["busy"] = False
            threading.Thread(target=ask, daemon=True, name="audio-present").start()
        return list(dict.fromkeys(touched))

    cls.check_streams = check_streams


patch_engine(sys.modules["soundboard.engine"].Engine)   # this runs at its end
