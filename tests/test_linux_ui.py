"""Linux: the main window's and the setup guide's cable buttons make the cable with
soundboard.linux.vcable (no installer, no download, no restart), and "game has no
microphone setting" makes it the default mic. The sound server is a stand-in."""
import sys

import pytest

from soundboard import engine
from soundboard.linux import vcable

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux only")

OUTS = ["Built-in Audio Analog Stereo", vcable.SINK_DESC]
INS = ["Blue Yeti Analog Stereo", vcable.SOURCE_DESC]


@pytest.fixture
def server(monkeypatch):
    """A sound server where the cable appears once vcable.install() runs."""
    state = {"cable": False, "installs": 0, "default_mic": "", "works": True}

    def list_devices(kind):
        names = INS if kind == "input" else OUTS
        if not state["cable"]:
            names = [n for n in names if "Onion Board" not in n]
        return [{"name": n, "index": i} for i, n in enumerate(names)]

    def install():
        state["installs"] += 1
        state["cable"] = state["works"]
        return state["works"]

    def default_mic():
        state["default_mic"] = vcable.SOURCE
        return state["works"]
    monkeypatch.setattr(engine, "list_devices", list_devices)
    monkeypatch.setattr(engine, "default_device_name", lambda kind: None)
    monkeypatch.setattr(engine, "rescan", lambda: True)
    monkeypatch.setattr(vcable, "install", install)
    monkeypatch.setattr(vcable, "make_default_mic", default_mic)
    for name in ("set_main_device", "set_mon_device", "set_mic_device"):
        monkeypatch.setattr(engine.Engine, name, lambda self, n, _name=name: None)
    return state


@pytest.fixture
def window(qapp, app_dir, server):
    from PySide6.QtCore import QEvent
    from soundboard.ui import mainwindow
    w = mainwindow.MainWindow()
    toasts = []
    w.toast = lambda text, kind="": toasts.append((kind, text))
    yield w, toasts
    w._load_thread.join(15)
    w.close()
    w.deleteLater()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)


def test_main_window_makes_the_cable(window, server):
    w, toasts = window
    assert w.btn_install.text() == "Make the virtual cable"
    w.install_cable()
    assert server["installs"] == 1 and server["cable"]
    assert toasts[-1][0] == "ok" and vcable.SOURCE_DESC in toasts[-1][1]


def test_main_window_says_when_it_cant(window, server):
    w, toasts = window
    server["works"] = False
    w.install_cable()
    assert toasts[-1][0] == "warn" and "PipeWire" in toasts[-1][1]


def test_game_with_no_mic_setting_gets_the_cable_as_default_mic(window, server):
    w, toasts = window
    w.open_windows_mic()
    assert server["default_mic"] == vcable.SOURCE and toasts[-1][0] == "ok"


def test_setup_guide_makes_the_cable_with_no_download_or_restart(window, server,
                                                                monkeypatch):
    from soundboard import net
    from soundboard.ui import setupwizard
    w, _ = window
    monkeypatch.setattr(net, "allowed", lambda feature: feature != "setup_downloads")
    setupwizard.resume_after_restart(True)   # no registry, no error
    wiz = setupwizard.SetupWizard(w)
    try:
        wiz.recheck_cable(rescan=False)
        assert not wiz.cable_ok()
        assert wiz.btn_cable.text() == "✚  Make it now (free, no download)"
        assert wiz.btn_cable.isEnabled()          # nothing to download: always allowed
        assert wiz.btn_restart.isHidden()
        wiz.install_cable()
        assert server["installs"] == 1 and wiz.cable_ok()
        assert w.cfg.main_device == vcable.SINK_DESC
        assert "Installed and connected" in wiz.cable_status.text()
    finally:
        wiz.done(0)
        wiz.deleteLater()


def test_settings_has_no_cable_download_switch(window):
    """The cable is made, not downloaded: its switch and its explanation are hidden;
    Tor's download switch beside it stays."""
    from PySide6.QtWidgets import QLabel
    from soundboard.settings import SettingsDialog
    w, _ = window
    d = SettingsDialog(w, "privacy")
    try:
        assert d.net_boxes["setup_downloads"].isHidden()
        assert not d.net_boxes["tor_download"].isHidden()
        [hint] = [lb for lb in d.findChildren(QLabel)
                  if lb.text() == d.NET_HINTS["setup_downloads"]]   # its VB-Cable text
        assert hint.isHidden()
        assert d.addon_label.text().startswith("Onion Watch") and \
            not d.addon_label.isVisibleTo(d)   # its card: no Triggers tab here
    finally:
        d.close()
        d.deleteLater()


def test_a_built_copy_that_cant_update_says_why_not_git_pull():
    from soundboard.linux.wording import update_phrases
    assert update_phrases(False, "") == []   # from source: git pull is right
    [(old, new), (old_html, new_html)] = update_phrases(True, "/opt/apps/OnionBoard.AppImage")
    assert "git pull" in old and "git pull" not in new and "(/opt/apps)" in new
    assert "<code>git pull</code>" in old_html and "release page" in new_html
    assert "isn't the AppImage" in update_phrases(True, "")[0][1]


def test_no_triggers_tab_until_onion_watch_runs_on_linux(window, qapp):
    """Hidden, not removed (the window still finds it), and it never asks for
    attention, even with triggers brought over from Windows."""
    w, _ = window
    i = w.tabs.indexOf(w.triggers)
    assert i >= 0 and not w.tabs.isTabVisible(i) and w.tabs.currentIndex() != i
    w._nudge_triggers(i)
    for _ in range(5):
        qapp.processEvents()
    assert "Onion Watch" not in w.status.text()


class _OverlayHost:
    def __init__(self):
        from soundboard.library import Config
        self.cfg = Config()
        self.audio = {}
        self.registered = 0

    def register_hotkeys(self):
        self.registered += 1

    def __getattr__(self, name):
        return lambda *a, **k: None


def test_overlay_preview_lets_clicks_through(qapp, monkeypatch):
    """Show preview is only to look at: upstream makes it click-through with a Windows
    window style, here it's Qt's flag, while the preview is up and no longer."""
    from PySide6.QtCore import Qt
    from soundboard import winkeys
    from soundboard.ui import mainwindow  # noqa: F401  (applies the Linux patches)
    from soundboard.ui.overlay import Overlay
    monkeypatch.setattr(winkeys, "exclusive_fullscreen", lambda: False)
    ov = Overlay(_OverlayHost(), None)
    try:
        def through():
            return bool(ov.window.windowHandle().flags() & Qt.WindowTransparentForInput)
        ov.preview(30)
        assert ov.window.isVisible() and through()
        ov._end_preview()
        assert not through()
        ov.preview(30)
        ov.open()            # the real overlay takes clicks
        assert ov.is_open and not through()
    finally:
        ov.shutdown()


XCB_CHECK = r"""
import ctypes, sys, time
from PySide6.QtWidgets import QApplication
app = QApplication([])
from soundboard import winkeys
from soundboard.ui import mainwindow
from soundboard.ui.overlay import Overlay
sys.path.insert(0, "tests")
from test_linux_ui import _OverlayHost
winkeys.exclusive_fullscreen = lambda: False
X, Xe = ctypes.CDLL("libX11.so.6"), ctypes.CDLL("libXext.so.6")
X.XOpenDisplay.restype = ctypes.c_void_p
Xe.XShapeGetRectangles.restype = ctypes.c_void_p
d = ctypes.c_void_p(X.XOpenDisplay(None))
ov = Overlay(_OverlayHost(), None)

def input_rects():
    for _ in range(10):
        app.processEvents()
        time.sleep(0.02)
    X.XSync(d, 0)
    n, order = ctypes.c_int(), ctypes.c_int()
    Xe.XShapeGetRectangles(d, ctypes.c_ulong(int(ov.window.winId())), 2,  # ShapeInput
                           ctypes.byref(n), ctypes.byref(order))
    return n.value
ov.preview(30)
during = input_rects()
ov._end_preview()
print("RECTS", during, input_rects())
ov.shutdown()
"""


def test_overlay_preview_has_no_input_shape_on_x11(tmp_path):
    """On a real X server (a private Xvfb): while the preview is up its window has an
    empty input shape, so a click goes to the window under it; then it's whole again."""
    import os
    import shutil
    import subprocess
    from pathlib import Path
    if not shutil.which("Xvfb"):
        pytest.skip("needs Xvfb")
    from xvfb import start_xvfb
    proc, n = start_xvfb()
    try:
        root = Path(__file__).resolve().parent.parent
        env = {**os.environ, "DISPLAY": f":{n}", "QT_QPA_PLATFORM": "xcb",
               "APPDATA": str(tmp_path), "XDG_DATA_HOME": str(tmp_path),
               "XDG_CONFIG_HOME": str(tmp_path)}
        r = subprocess.run([sys.executable, "-c", XCB_CHECK], cwd=root, env=env,
                           capture_output=True, text=True, timeout=60)
    finally:
        proc.kill()
        proc.wait()
    if "could not load the Qt platform plugin" in r.stderr.lower():
        pytest.skip("Qt's xcb plugin can't load here (libxcb-icccm4 / -keysyms1)")
    line = [s for s in r.stdout.splitlines() if s.startswith("RECTS")]
    assert line, r.stderr[-2000:]
    during, after = map(int, line[0].split()[1:])
    assert during == 0 and after >= 1


def test_the_triggers_timer_firing_mid_build_is_no_crash(qapp, app_dir, server, monkeypatch):
    """The window starts load_triggers' 50 ms timer half-way through being built, and
    the splash's pump runs pending events after that: on a slow PC (the Fedora VM, at
    every start) the timer fired before __init__ had set _shut_down (AttributeError,
    logged as a crash). Upstream's code; the Linux hook gives it a class default."""
    import time

    from PySide6.QtCore import QEvent

    from soundboard.ui import mainwindow, splash

    def slow_pump():
        time.sleep(mainwindow.TRIGGERS_LOAD_MS / 1000 + 0.02)
        qapp.processEvents()
    monkeypatch.setattr(splash, "pump", slow_pump)
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *e: errors.append(e[1]))
    w = mainwindow.MainWindow()
    try:
        assert errors == []
    finally:
        w._load_thread.join(15)
        w.close()
        w.deleteLater()
        qapp.sendPostedEvents(None, QEvent.DeferredDelete)
