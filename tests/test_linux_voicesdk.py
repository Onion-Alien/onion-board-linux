"""The game in front on Linux (soundboard.linux.voicesdk): the X11 active window's
process, a Proton game's Windows .exe from its command line, and the watcher
suggesting its voice engine. A private Xvfb and real child processes, nothing of the
desktop's."""
import ctypes
import os
import shutil
import subprocess
import sys
import time
from ctypes import c_int, c_long, c_ulong, c_void_p

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux only")

SLEEP = shutil.which("sleep") or "/bin/sleep"


@pytest.fixture
def child():
    """A process of ours whose argv[0] (what Wine shows a game as) is ours to pick."""
    procs = []

    def start(argv0: str, env: dict | None = None) -> int:
        p = subprocess.Popen([argv0, "60"], executable=SLEEP, env=env)
        procs.append(p)
        # Popen returns as exec starts; the kernel fills in the new command line a
        # moment later (an empty cmdline until then, under load)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with open(f"/proc/{p.pid}/cmdline", "rb") as f:
                if f.read().startswith(argv0.encode()):
                    break
            time.sleep(0.01)
        return p.pid
    yield start
    for p in procs:
        p.kill()
        p.wait()


def test_a_proton_games_exe_from_its_command_line(child, tmp_path):
    from soundboard.linux.voicesdk import exe_of
    assert exe_of(child("Z:\\srv\\Games\\Hunt\\Hunt.exe")) == "/srv/Games/Hunt/Hunt.exe"
    pfx = tmp_path / "pfx"
    (pfx / "drive_c").mkdir(parents=True)
    pid = child("C:\\Games\\Lethal\\Lethal.exe", env={**os.environ, "WINEPREFIX": str(pfx)})
    assert exe_of(pid) == str(pfx / "drive_c" / "Games" / "Lethal" / "Lethal.exe")


def test_a_native_program_is_its_exe(child):
    from soundboard.linux.voicesdk import exe_of
    assert exe_of(child("sleep")) == os.path.realpath(SLEEP)
    assert exe_of(2 ** 22 + 1) == ""   # no such process


@pytest.mark.parametrize("path,system", [
    ("/usr/bin/plasmashell", True), ("/usr/lib/firefox/firefox", True),
    ("/srv/wine/drive_c/windows/explorer.exe", True),
    ("/srv/steam/steamapps/common/Hunt/Hunt.exe", False),
    ("/srv/Games/native/game.x86_64", False), ("", False)])
def test_system_programs_dont_count(path, system):
    from soundboard import voicesdk
    assert voicesdk._is_system(path) is system


class _X:
    """Just enough of Xlib to play the window manager: a window with a _NET_WM_PID,
    made the root's _NET_ACTIVE_WINDOW."""

    def __init__(self):
        x = ctypes.CDLL("libX11.so.6")   # its own handle: its prototypes are ours
        x.XOpenDisplay.restype = c_void_p
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XDefaultRootWindow.restype = c_ulong
        x.XDefaultRootWindow.argtypes = [c_void_p]
        x.XCreateSimpleWindow.restype = c_ulong
        x.XCreateSimpleWindow.argtypes = [c_void_p, c_ulong, c_int, c_int, ctypes.c_uint,
                                          ctypes.c_uint, ctypes.c_uint, c_ulong, c_ulong]
        x.XInternAtom.restype = c_ulong
        x.XInternAtom.argtypes = [c_void_p, ctypes.c_char_p, c_int]
        x.XChangeProperty.argtypes = [c_void_p, c_ulong, c_ulong, c_ulong, c_int, c_int,
                                      c_void_p, c_int]
        x.XSync.argtypes = [c_void_p, c_int]
        x.XCloseDisplay.argtypes = [c_void_p]
        self.x, self.dpy = x, x.XOpenDisplay(None)
        assert self.dpy
        self.root = x.XDefaultRootWindow(self.dpy)

    def _set(self, win, prop, kind, value):
        data = (c_long * 1)(value)
        self.x.XChangeProperty(self.dpy, win, self.x.XInternAtom(self.dpy, prop, 0), kind, 32,
                               0, ctypes.cast(data, c_void_p), 1)

    def activate(self, pid: int | None):
        win = self.x.XCreateSimpleWindow(self.dpy, self.root, 0, 0, 10, 10, 0, 0, 0)
        if pid is not None:
            self._set(win, b"_NET_WM_PID", 6, pid)          # XA_CARDINAL
        self._set(self.root, b"_NET_ACTIVE_WINDOW", 33, win)   # XA_WINDOW
        self.x.XSync(self.dpy, 0)

    def close(self):
        self.x.XCloseDisplay(self.dpy)


@pytest.fixture
def xwm(monkeypatch):
    if not shutil.which("Xvfb"):
        pytest.skip("needs Xvfb")
    from xvfb import start_xvfb
    from soundboard.linux import voicesdk
    proc, n = start_xvfb()
    monkeypatch.setenv("DISPLAY", f":{n}")
    monkeypatch.setattr(voicesdk, "_dpy", None)
    wm = _X()
    yield wm
    if voicesdk._dpy is not None:
        voicesdk._dpy.close()
        voicesdk._dpy = None
    wm.close()
    proc.terminate()
    proc.wait(5)


def test_the_window_in_front_names_its_game(xwm, child):
    from soundboard.linux import voicesdk   # conftest stubs soundboard.voicesdk's
    assert voicesdk.foreground_process() == (0, "")    # no active window yet
    pid = child("Z:\\games\\Hunt\\Hunt.exe")
    xwm.activate(pid)
    assert voicesdk.foreground_process() == (pid, "/games/Hunt/Hunt.exe")
    xwm.activate(os.getpid())                           # our own window
    assert voicesdk.foreground_process() == (0, "")
    xwm.activate(None)                                  # a window that names no process
    assert voicesdk.foreground_process() == (0, "")


def test_the_watcher_suggests_the_game_in_fronts_voice_engine(xwm, child):
    from soundboard import voicesdk
    from soundboard.linux.voicesdk import foreground_process
    pid = child("Z:\\games\\Hunt\\Hunt.exe")
    xwm.activate(pid)
    w = voicesdk.Watcher(foreground=foreground_process,
                         scanner=lambda p: "game" if p.endswith("Hunt.exe") else None)
    deadline = time.monotonic() + 5
    while w.poll() != "game" and time.monotonic() < deadline:   # the scan is on a thread
        time.sleep(0.02)
    assert w.suggestion == "game"
    xwm.activate(child("/usr/bin/plasmashell"))         # the desktop: still the game
    assert w.poll() == "game"
