"""Linux side of soundboard.appaudio: one program's sound (the Apps tab), or every
program's but Onion Board's (instant replay), from PipeWire.

Each program's playback is a PipeWire stream node ("Stream/Output/Audio", with the
process id that made it). `pw-record --target <node>` records a copy of one node: the
program keeps playing where it was. A program can have several nodes (a browser: one
per tab playing), and they come and go, so AppCapture looks for its nodes again every
RESCAN_S, runs a recorder per node and mixes them.

Needs PipeWire (pw-dump, pw-record); on plain PulseAudio supported() says so.
Levels for the Apps tab's meters aren't available without capturing every program,
so PeakWatcher reports none and the rows show their playing / quiet state instead.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import deque

import numpy as np

log = logging.getLogger(__name__)

__all__ = ["supported", "list_apps", "default_output_name", "process_path", "is_running",
           "root_pid", "PeakWatcher", "AppCapture"]

SR = 48000
RESCAN_S = 1.0
CHUNK = 480                # frames per read: 10 ms
PREBUFFER = SR // 25       # 40 ms per stream before mixing starts, against jitter
MAX_BUFFER = SR // 4       # a stream more than 250 ms ahead (clock drift): drop the oldest
TIMEOUT_S = 5.0


def _a():
    from soundboard import appaudio
    return appaudio


def supported() -> tuple[bool, str]:
    if not (shutil.which("pw-dump") and shutil.which("pw-record")):
        return False, ("Capturing a program's audio needs PipeWire (with its pw-dump and "
                       "pw-record tools, in the pipewire or pipewire-bin package).")
    return True, ""


# ------------------------------------------------------------------ processes
def process_path(pid: int) -> str:
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return ""


def is_running(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


def _ppid(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as f:
            return int(f.read().rsplit(")", 1)[1].split()[1])
    except (OSError, IndexError, ValueError):
        return 0


# Linux names of the shared helpers the Windows version folds into the program that
# started them (Steam's store and overlay, Qt WebEngine's renderer)
HELPERS = {"steamwebhelper", "qtwebengineprocess"}
_upstream = sys.modules["soundboard.appaudio"]   # this runs at its end
_upstream.HELPER_EXES.update(HELPERS)
_upstream_root_pid = _upstream.root_pid


def _process_table(pids) -> dict[int, tuple[int, str]]:
    """pid -> (parent pid, program name in lower case), as the Windows table, for
    `pids` and their parents up the tree (all root_pid reads). init / systemd are
    left out, so nothing is taken for a program they started."""
    table: dict[int, tuple[int, str]] = {}
    for pid in pids:
        while pid > 1 and pid not in table:
            name = os.path.basename(process_path(pid)).lower()
            if not name or name == "systemd":
                break
            table[pid] = (_ppid(pid), name)
            pid = table[pid][0]
    return table


def root_pid(pid: int, table=None) -> int:
    """The top of the process's tree of the same program (a browser's tab processes
    -> the browser), a shared helper going to the program that started it: the
    Windows version's rules, on a table of this system's processes."""
    return _upstream_root_pid(pid, _process_table([pid]) if table is None else table)


def _in_tree(pid: int, root: int) -> bool:
    seen = 0
    while pid > 1 and seen < 64:
        if pid == root:
            return True
        pid = _ppid(pid)
        seen += 1
    return False


# ------------------------------------------------------------------ PipeWire
def stream_nodes(dump: list | None = None) -> list[dict]:
    """Playback streams: [{serial, pid, app, binary, state, sink}]."""
    if dump is None:
        try:
            p = subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=TIMEOUT_S)
            dump = json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() else []
        except (OSError, subprocess.TimeoutExpired, ValueError):
            log.debug("pw-dump failed", exc_info=True)
            dump = []
    out = []
    for o in dump:
        if o.get("type") != "PipeWire:Interface:Node":
            continue
        info = o.get("info") or {}
        props = info.get("props") or {}
        if props.get("media.class") != "Stream/Output/Audio":
            continue
        try:
            pid = int(props.get("application.process.id") or 0)
        except (TypeError, ValueError):
            pid = 0
        out.append({"serial": str(props.get("object.serial") or o.get("id")), "pid": pid,
                    "app": str(props.get("application.name") or ""),
                    "binary": str(props.get("application.process.binary") or ""),
                    "state": str(info.get("state") or ""),
                    "sink": str(props.get("target.object") or props.get("node.target") or "")})
    return out


def list_apps() -> list:
    """Every program with a playback stream, this process left out, grouped by
    process tree (App.pid is the tree's root)."""
    App = _a().App
    me = os.getpid()
    apps: dict[int, object] = {}
    nodes = [n for n in stream_nodes()
             if n["pid"] and n["pid"] != me and not _in_tree(n["pid"], me)]
    table = _process_table(n["pid"] for n in nodes)
    for n in nodes:
        root = root_pid(n["pid"], table)
        app = apps.get(root)
        if app is None:
            path = process_path(root)
            exe = os.path.basename(path) or n["binary"] or n["app"] or f"pid {root}"
            app = apps[root] = App(pid=root, exe=exe, path=path, title=n["app"])
        app.session_pids.add(n["pid"])
        app.active = app.active or n["state"] == "running"
    return sorted(apps.values(), key=lambda a: (not a.active, a.name.lower()))


def default_output_name() -> str | None:
    from soundboard.linux import audio
    audio.refresh()
    return audio.default_device_name("output")


class PeakWatcher:
    """No per-program meters on Linux (see the module's note): peak() is None, so the
    Apps tab falls back to each program's playing state."""

    def __init__(self, interval: float = 0.05, rescan: float = 1.5):
        self.interval, self.rescan = interval, rescan

    def peak(self, pid: int) -> float | None:
        return None

    def start(self):
        pass

    def stop(self):
        pass


# ------------------------------------------------------------------ capture
class _Reader:
    """One `pw-record --target <serial>`, its audio queued as (n, 2) float32."""

    def __init__(self, serial: str):
        self.serial = serial
        self.buf: deque[np.ndarray] = deque()
        self.frames = 0
        self.primed = False
        self.lock = threading.Lock()
        self.proc = subprocess.Popen(
            ["pw-record", "--target", serial, "--rate", str(SR), "--channels", "2",
             "--format", "f32", "--latency", "20ms",
             "--properties", "{ application.name = \"Onion Board\" node.dont-reconnect = true }",
             "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self.thread = threading.Thread(target=self._read, daemon=True,
                                       name=f"pw-record-{serial}")
        self.thread.start()

    def _read(self):
        rest = b""
        while True:
            try:
                b = self.proc.stdout.read(8 * CHUNK)
            except (OSError, ValueError):
                break
            if not b:
                break
            b = rest + b
            n = len(b) // 8
            rest = b[n * 8:]
            if n:
                x = np.frombuffer(b[:n * 8], np.float32).reshape(n, 2).copy()
                with self.lock:
                    self.buf.append(x)
                    self.frames += n
                    while self.frames > MAX_BUFFER and len(self.buf) > 1:
                        self.frames -= len(self.buf.popleft())

    def take(self, n: int) -> np.ndarray | None:
        """`n` frames (padded with silence if short), or None while still priming."""
        with self.lock:
            if not self.primed:
                if self.frames < PREBUFFER:
                    return None
                self.primed = True
            out = np.zeros((n, 2), np.float32)
            got = 0
            while got < n and self.buf:
                x = self.buf[0]
                k = min(n - got, len(x))
                out[got:got + k] = x[:k]
                got += k
                if k == len(x):
                    self.buf.popleft()
                else:
                    self.buf[0] = x[k:]
            self.frames -= got
            return out

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.thread.join(1)


class AppCapture:
    """Same interface as the Windows AppCapture: `start()`, `stop()`, `running`,
    `error`, `ended`, `frames`, and `sink((n, 2) float32 at 48 kHz)` called from its
    own thread. include_tree=False captures every program *but* `pid`'s tree (instant
    replay passes its own pid)."""

    def __init__(self, pid: int, sink, include_tree: bool = True, name: str = ""):
        self.pid, self.sink, self.include_tree = int(pid), sink, include_tree
        self.name = name or str(pid)
        self.error: str | None = None
        self.ended = False
        self.frames = 0
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._readers: dict[str, _Reader] = {}
        self._thread = threading.Thread(target=self._run, name=f"appcapture-{pid}",
                                        daemon=True)

    def start(self, timeout: float = 6.0) -> bool:
        if self.include_tree and not is_running(self.pid):   # whatever the sound server
            self.error = "That program isn't running any more."
            self.ended = True
            return False
        ok, why = supported()
        if not ok:
            self.error = why
            return False
        self._thread.start()
        if not self._ready.wait(timeout):
            self.error = "PipeWire didn't answer in time. Switch Send on to try again."
            self.stop()
            return False
        return self.error is None

    def stop(self):
        self._stop.set()
        if self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(3)

    @property
    def running(self) -> bool:
        return self._thread.is_alive() and self.error is None and not self.ended

    def _wanted(self) -> set[str]:
        me = os.getpid()
        out = set()
        for n in stream_nodes():
            if not n["pid"]:
                continue
            mine = _in_tree(n["pid"], self.pid)
            if self.include_tree and mine:
                out.add(n["serial"])
            elif not self.include_tree and not mine and not _in_tree(n["pid"], me):
                out.add(n["serial"])
        return out

    def _sync(self):
        want = self._wanted()
        for s in list(self._readers):
            r = self._readers[s]
            if s not in want or not r.alive:
                r.stop()
                del self._readers[s]
        for s in want - set(self._readers):
            try:
                self._readers[s] = _Reader(s)
            except OSError as e:
                log.warning("app capture %s: pw-record wouldn't start: %s", self.name, e)

    def _run(self):
        try:
            self._sync()
            self._ready.set()
            next_scan = time.monotonic() + RESCAN_S
            t0 = time.monotonic()
            emitted = 0
            while not self._stop.wait(0.01):
                now = time.monotonic()
                if now >= next_scan:
                    self._sync()
                    next_scan = now + RESCAN_S
                    if self.include_tree and not is_running(self.pid):
                        self.ended = True
                        log.info("app capture %s: the program closed", self.name)
                        return
                n = int((now - t0) * SR) - emitted
                if n <= 0:
                    continue
                emitted += n
                parts = [x for x in (r.take(n) for r in list(self._readers.values()))
                         if x is not None]
                if not parts:
                    continue
                mix = parts[0] if len(parts) == 1 else np.sum(parts, axis=0)
                self.frames += n
                try:
                    self.sink(mix)
                except Exception:  # noqa: BLE001 - a bad block mustn't end the capture
                    log.exception("app capture %s: sink failed", self.name)
        except Exception as e:  # noqa: BLE001
            from soundboard import errors
            self.error = errors.plain(e)
            log.exception("app capture %s failed", self.name)
        finally:
            self._ready.set()
            for r in self._readers.values():
                r.stop()
            self._readers.clear()
