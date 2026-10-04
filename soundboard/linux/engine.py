"""Linux side of soundboard.engine: the device lists are the sound server's
(soundboard.linux.audio), and streams on them open through PortAudio's "pulse"
device (`sd` here replaces the engine's sounddevice). find_device, virtual_outputs
and virtual_mic_for are built on list_devices, so they need no Linux version."""
from __future__ import annotations

import logging

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

