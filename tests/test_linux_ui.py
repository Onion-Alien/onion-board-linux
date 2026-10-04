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
