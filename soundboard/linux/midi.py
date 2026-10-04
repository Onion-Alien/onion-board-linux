"""MIDI pad controllers on Linux: ALSA raw MIDI (/dev/snd/midiC<card>D<device>),
no extra packages. The same backend interface as midi.WinMM: devices(), open(index,
key), close(handle), and on_message(key, packed short message) / on_closed(key)
called from the device's reader thread.

A raw MIDI device opened by another program fails with EBUSY, which is midi.Busy,
the same "in use by another program" the Windows driver gives.
"""
from __future__ import annotations

import errno
import logging
import os
import re
import select
import threading
from pathlib import Path

log = logging.getLogger(__name__)

_DEV = re.compile(r"midiC(\d+)D(\d+)$")
# data bytes that follow each status (high nibble); system messages are skipped
_LEN = {0x80: 2, 0x90: 2, 0xA0: 2, 0xB0: 2, 0xC0: 1, 0xD0: 1, 0xE0: 2}


def _name(card: int, dev: int) -> str:
    base = Path(f"/proc/asound/card{card}")
    for f in (base / f"midi{dev}", base / "id"):
        try:
            line = f.read_text(errors="ignore").splitlines()[0].strip()
        except (OSError, IndexError):
            continue
        if line:
            return line if dev == 0 else f"{line} {dev + 1}"
    return f"MIDI {card}-{dev}"


class Parser:
    """Raw MIDI bytes -> packed short messages (status | d1 << 8 | d2 << 16), with
    running status. Realtime bytes (clock…) and sysex are dropped."""

    def __init__(self):
        self.status = 0
        self.data: list[int] = []
        self.sysex = False

    def feed(self, chunk: bytes) -> list[int]:
        out = []
        for b in chunk:
            if b >= 0xF8:
                continue                      # realtime: may sit inside any message
            if b == 0xF0:
                self.sysex, self.status, self.data = True, 0, []
                continue
            if b >= 0x80:
                self.sysex = False
                self.status, self.data = (b, []) if b < 0xF0 else (0, [])
                continue
            if self.sysex or not self.status:
                continue
            self.data.append(b)
            need = _LEN[self.status & 0xF0]
            if len(self.data) == need:
                d1, d2 = self.data[0], self.data[1] if need == 2 else 0
                out.append(self.status | d1 << 8 | d2 << 16)
                self.data = []                 # running status: keep self.status
        return out


class _Open:
    def __init__(self, fd: int, key: int):
        self.fd, self.key = fd, key
        self.stop_r, self.stop_w = os.pipe()
        self.thread: threading.Thread | None = None


class AlsaRawMidi:
    slow = False   # listing is a directory read

    def __init__(self, root: str = "/dev/snd"):
        self.on_message = lambda key, msg: None
        self.on_closed = lambda key: None
        self.root = Path(root)
        self._paths: list[Path] = []

    def devices(self) -> list[str]:
        found = []
        try:
            entries = list(self.root.iterdir())
        except OSError:
            entries = []
        for p in entries:
            m = _DEV.match(p.name)
            if m:
                found.append((int(m[1]), int(m[2]), p))
        found.sort()
        self._paths = [p for _c, _d, p in found]
        return [_name(c, d) for c, d, _p in found]

    def open(self, index: int, key: int):
        from soundboard.midi import Busy
        if not self._paths:
            self.devices()
        try:
            fd = os.open(self._paths[index], os.O_RDONLY | os.O_NONBLOCK)
        except IndexError:
            raise OSError(errno.ENODEV, "unplugged") from None
        except OSError as e:
            if e.errno == errno.EBUSY:
                raise Busy(e.errno, "in use by another program") from None
            raise
        h = _Open(fd, key)
        h.thread = threading.Thread(target=self._read, args=(h,), daemon=True,
                                    name=f"midi-{key}")
        h.thread.start()
        return h

    def close(self, h: _Open):
        try:
            os.write(h.stop_w, b"x")
        except OSError:
            pass
        if h.thread is not None and h.thread is not threading.current_thread():
            h.thread.join(1)

    def _read(self, h: _Open):
        parser = Parser()
        lost = False
        try:
            while True:
                r, _w, _x = select.select([h.fd, h.stop_r], [], [])
                if h.stop_r in r:
                    break
                try:
                    chunk = os.read(h.fd, 256)
                except BlockingIOError:
                    continue
                except OSError:
                    lost = True                # unplugged
                    break
                if not chunk:
                    lost = True
                    break
                for msg in parser.feed(chunk):
                    try:
                        self.on_message(h.key, msg)
                    except Exception:  # noqa: BLE001 - never let it end the reader
                        log.exception("MIDI callback failed")
        finally:
            for fd in (h.fd, h.stop_r, h.stop_w):
                try:
                    os.close(fd)
                except OSError:
                    pass
            if lost:
                self.on_closed(h.key)
