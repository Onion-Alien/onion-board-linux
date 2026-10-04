"""Linux hotkeys (soundboard.linux.keys) against a real X server: a private Xvfb,
started here, so nothing reaches the developer's own desktop. Skipped on Windows
and where Xvfb isn't installed."""
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from conftest import process_events

pytestmark = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("Xvfb"),
                                reason="needs Linux and Xvfb")


@pytest.fixture(scope="module")
def xserver():
    for n in range(91, 120):
        if not os.path.exists(f"/tmp/.X11-unix/X{n}") and not os.path.exists(f"/tmp/.X{n}-lock"):
            break
    proc = subprocess.Popen(["Xvfb", f":{n}", "-nolisten", "tcp", "-screen", "0", "640x480x24"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    old = os.environ.get("DISPLAY")
    os.environ["DISPLAY"] = f":{n}"
    # the socket appears before Xvfb answers (it's still loading its keymap on a slow
    # CI runner): wait until a connection really opens
    from soundboard.linux import x11
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if os.path.exists(f"/tmp/.X11-unix/X{n}"):
            try:
                x11.Display().close()
                break
            except OSError:
                pass
        time.sleep(0.1)
    from soundboard.linux import keys
    keys.close_shared()
    made = []
    real = keys.Hotkeys.__init__

    def tracked(self, *a, **k):   # every Hotkeys made here lets go before Xvfb ends
        made.append(self)
        real(self, *a, **k)
    keys.Hotkeys.__init__ = tracked
    yield f":{n}"
    keys.Hotkeys.__init__ = real
    for hk in made:
        hk.stop(wait=2)
    keys.close_shared()
    if old is None:
        os.environ.pop("DISPLAY", None)
    else:
        os.environ["DISPLAY"] = old
    proc.terminate()
    proc.wait(5)


class _NoMidi:
    """MidiIn stand-in: no devices, no timers."""
    def __init__(self):
        from PySide6.QtCore import QObject, Signal

        class S(QObject):
            pressed = Signal(str)
            released = Signal(str)
        self._s = S()
        self.pressed, self.released = self._s.pressed, self._s.released

    def want(self, _devices):
        pass

    def close_all(self):
        pass


def test_winkeys_is_the_linux_version():
    from soundboard import winkeys
    from soundboard.linux import keys
    assert winkeys.Hotkeys is keys.Hotkeys
    assert winkeys.parse("ctrl+alt+s") == (0x3, 0x53)   # the portable parts stay


def test_vk_keysym_round_trip():
    from soundboard import winkeys
    from soundboard.linux import x11
    for name, vk in winkeys.VK.items():
        ks = x11.vk_to_keysym(vk)
        assert ks is not None, name
        assert x11.keysym_to_vk(ks) == vk or name in ("enter",), name


def test_hotkey_fires_and_releases(qapp, xserver):
    from soundboard import winkeys
    hk = winkeys.Hotkeys(_NoMidi())
    assert hk.alive
    got = []
    hk.fired.connect(lambda a: got.append(("fired", a)))
    hk.released.connect(lambda a: got.append(("released", a)))
    failed = []
    hk.failed_changed.connect(failed.append)
    hk.register({"ctrl+alt+s": "stop", "f9": "nine"})
    assert process_events(qapp, lambda: failed, 3)
    assert failed[-1] == []

    assert winkeys.press("ctrl+alt+s")
    assert process_events(qapp, lambda: ("fired", "stop") in got, 3)
    assert winkeys.is_down(winkeys.VK["s"])
    assert winkeys.release("ctrl+alt+s")
    assert process_events(qapp, lambda: ("released", "stop") in got, 3)
    assert not winkeys.is_down(winkeys.VK["s"])

    winkeys.press("f9")
    winkeys.release("f9")
    assert process_events(qapp, lambda: ("released", "nine") in got, 3)
    assert got.count(("fired", "stop")) == 1   # no auto-repeat duplicates

    # without its modifiers it isn't the hotkey
    got.clear()
    winkeys.press("s")
    winkeys.release("s")
    process_events(qapp, lambda: False, 0.3)
    assert got == []
    hk.stop()


def test_combo_another_program_holds_is_reported(qapp, xserver):
    from soundboard import winkeys
    first = winkeys.Hotkeys(_NoMidi())
    second = winkeys.Hotkeys(_NoMidi())
    f1, f2 = [], []
    first.failed_changed.connect(f1.append)
    second.failed_changed.connect(f2.append)
    first.register({"ctrl+shift+f5": "a"})
    assert process_events(qapp, lambda: f1, 3)
    second.register({"ctrl+shift+f5": "b", "ctrl+shift+f6": "c"})
    assert process_events(qapp, lambda: f2, 3)
    assert f1[-1] == [] and f2[-1] == ["ctrl+shift+f5"]
    first.stop()
    second.stop()


def test_no_display_means_keys_fail_but_midi_works(qapp, monkeypatch):
    from soundboard import winkeys
    from soundboard.linux import x11
    monkeypatch.setattr(x11, "available", lambda: False)
    hk = winkeys.Hotkeys(_NoMidi())
    failed = []
    hk.failed_changed.connect(failed.append)
    hk.register({"f9": "x", "midi:note 36:LPD8": "y"})
    assert failed[-1] == ["f9"]
    got = []
    hk.fired.connect(got.append)
    hk.midi.pressed.emit("midi:note 36:LPD8")
    assert got == ["y"]


def test_event_vk_uses_the_unshifted_key(qapp, xserver):
    from soundboard import winkeys
    from soundboard.linux import keys

    class E:
        def __init__(self, code, ks):
            self.code, self.ks = code, ks

        def nativeScanCode(self):
            return self.code

        def nativeVirtualKey(self):
            return self.ks

    d = keys._shared()
    kc1 = d.keycode(winkeys.VK["1"])
    assert winkeys.event_vk(E(kc1, 0x21)) == winkeys.VK["1"]   # Shift+1 reports "!"
    assert winkeys.event_vk(E(0, 0xFFC6)) == winkeys.VK["f9"]  # keysym fallback


def test_the_x_server_going_away_doesnt_end_the_app(qapp, tmp_path):
    """Xlib exits the process when its X server vanishes; the app must carry on (a
    logout, or this test's own Xvfb). Run in a child so a failure can't end pytest."""
    script = tmp_path / "xgone.py"
    script.write_text(textwrap.dedent(f"""
        import os, subprocess, sys, time
        sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        n = int(sys.argv[1])
        x = subprocess.Popen(["Xvfb", f":{{n}}", "-nolisten", "tcp"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while not os.path.exists(f"/tmp/.X11-unix/X{{n}}"):
            time.sleep(0.05)
        os.environ["DISPLAY"] = f":{{n}}"
        from PySide6.QtWidgets import QApplication
        app = QApplication([])
        from soundboard import winkeys
        hk = winkeys.Hotkeys()
        hk.register({{"f9": "x"}})
        winkeys.is_down(0x41)            # the shared connection too
        app.processEvents()
        time.sleep(0.3)
        x.kill(); x.wait()
        time.sleep(0.5)
        winkeys.is_down(0x41)
        app.processEvents()
        print("still here", flush=True)
    """))
    for n in range(121, 160):
        if not os.path.exists(f"/tmp/.X11-unix/X{n}"):
            break
    out = subprocess.run([sys.executable, str(script), str(n)], capture_output=True,
                         text=True, timeout=60)
    assert "still here" in out.stdout, out.stderr[-2000:]
