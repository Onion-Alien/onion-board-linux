"""Linux: "Straight into my mic" (1.9.0's mic effect, soundboard/directmic.py) isn't
here yet, so the app runs as before it: the cable is the route, the mic is never
offered, and nothing asks for admin or touches a Windows path
(soundboard/linux/directmic.py, linux/library.py, linux/ui.py). The update check
never takes 1.9.1's Windows update copy."""
import json
import sys

import pytest
from test_linux_ui import server, window  # noqa: F401 - fixtures

from soundboard import directmic, library, updates

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux only")


def test_the_mic_is_never_ready_and_never_asks_for_admin():
    assert directmic.AVAILABLE is False
    assert directmic.status(None) == "missing" and directmic.status("Blue Yeti") == "missing"
    assert not directmic.works(directmic.status())
    assert directmic.capture_endpoints() == [] and directmic.installed_on() == []
    assert "virtual cable" in directmic.install("Blue Yeti")
    assert directmic.uninstall() is None
    # the uninstaller's "remove" has nothing to take off; the admin steps don't exist
    assert directmic.cli(["remove"]) == 0
    assert directmic.cli(["install", "{a}"]) == 2 and directmic.cli(["uninstall"]) == 2


def test_new_and_old_users_stay_on_the_cable(app_dir):
    assert "mic" not in library.ROUTES
    assert library.Config.load().route == "cable"   # no settings yet: a first start
    assert library.Config.first_start().route == "cable"
    # 1.9.1 moves cable settings to the mic once: here they stay on the cable
    assert library.Config.from_raw({"version": 4}).route == "cable"
    assert library.Config.from_raw({"version": 4, "route": "cable"}).route == "cable"
    assert library.Config.from_raw({"version": 4, "route": "device"}).route == "device"
    assert library.Config.from_raw({"version": 4, "route": "off"}).route == "off"


def test_settings_from_windows_on_the_mic_come_back_on_the_cable_and_keep_it(app_dir):
    cfg = library.Config.from_raw({"version": 4, "route": "mic", "mic_first": True})
    assert cfg.route == "cable"
    # written back as it was, like a newer version's route: Windows (or a Linux with
    # the mic) opening these settings again finds its choice
    assert cfg.to_raw()["route"] == "mic"


def test_setup_never_offers_the_mic(window, qapp):  # noqa: F811
    from soundboard.ui import mainwindow, setupwizard
    w, _ = window
    assert [k for _t, k in mainwindow.ROUTE_CHOICES] == ["cable", "device", "off"]
    assert w.cfg.route == "cable"
    w._update_flow()
    assert w.btn_attach.isHidden()
    wiz = setupwizard.SetupWizard(w)
    try:
        wiz.recheck_cable(rescan=False)
        assert wiz.btn_attach.isHidden()
        texts = " ".join(lbl.text() for lbl in wiz.findChildren(setupwizard.QLabel))
        assert "Straight into <b>your mic</b>" not in texts
        assert "Windows" not in texts
    finally:
        wiz.done(0)
        wiz.deleteLater()


def test_whats_new_says_nothing_of_the_mic():
    from soundboard.ui import whatsnew
    versions = [n.version for n in whatsnew.NOTES]
    assert "1.9.1" not in versions and "1.9.0" in versions
    for n in whatsnew.NOTES:
        for _icon, title, text in n.items:
            words = f"{n.headline} {title} {text}".lower()
            assert "straight into" not in words and "into the mic" not in words
    nine = next(n for n in whatsnew.NOTES if n.version == "1.9.0")
    assert "cable" not in nine.headline.lower() and nine.items


@pytest.mark.parametrize("with_update_copy", [False, True])
def test_update_now_never_takes_the_windows_update_copy(monkeypatch, with_update_copy):
    """1.9.1 releases carry OnionBoardSetup-update.exe for Update now (counted apart
    from new downloads): Linux takes its own AppImage, or the AppImage's update copy
    when the release has one."""
    base = "https://github.com/Onion-Alien/onion-board/releases/download/v9.0.0/"
    assets = [{"name": n, "browser_download_url": base + n, "digest": "sha256:" + c * 64,
               "size": 1} for n, c in (("OnionBoardSetup.exe", "0"),
                                       ("OnionBoardSetup-update.exe", "1"),
                                       ("OnionBoard-x86_64.AppImage", "2"))]
    if with_update_copy:
        assets.append({"name": "OnionBoard-x86_64-update.AppImage", "size": 1,
                       "browser_download_url": base + "OnionBoard-x86_64-update.AppImage",
                       "digest": "sha256:" + "3" * 64})
    data = {"tag_name": "v9.0.0", "html_url": "https://github.com/x", "body": "notes",
            "assets": assets}
    monkeypatch.setattr(updates, "_get", lambda url, *_f: json.loads(json.dumps(data)))
    rel = updates.latest()
    assert rel.asset_url.endswith("-update.AppImage" if with_update_copy
                                  else "OnionBoard-x86_64.AppImage")
    assert ".exe" not in rel.asset_url


def test_resetting_devices_goes_back_to_the_cable(app_dir):
    from soundboard import reset
    raw = library.Config().to_raw()
    raw["route"] = "a-newer-route"
    library.CONFIG_PATH.write_text(json.dumps(raw), encoding="utf-8")
    reset.schedule_reset([reset.DEVICES])
    reset.run_pending()
    assert json.loads(library.CONFIG_PATH.read_text(encoding="utf-8"))["route"] == "cable"
