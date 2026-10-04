"""soundboard/linux/updates.py: the AppImage updates itself. GitHub's answers are
faked; the waiter that starts the new copy runs for real, on a stand-in AppImage."""
import hashlib
import os
import subprocess
import sys
import time

import pytest
from platform_hooks import REAL

from soundboard import updates

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux self-update")

APPIMAGE = b"\x7fELF new version"
SHA = hashlib.sha256(APPIMAGE).hexdigest()
URL = ("https://github.com/Onion-Alien/onion-board/releases/download/v9.0.0/"
       "OnionBoard-x86_64.AppImage")


def _release_json(**asset):
    win = {"name": "OnionBoardSetup.exe", "digest": "sha256:" + "0" * 64,
           "browser_download_url": URL.replace("OnionBoard-x86_64.AppImage",
                                               "OnionBoardSetup.exe")}
    a = {"name": "OnionBoard-x86_64.AppImage", "browser_download_url": URL,
         "digest": f"sha256:{SHA}", "size": len(APPIMAGE)}
    a.update(asset)
    return {"tag_name": "v9.0.0", "html_url": "https://github.com/x", "body": "notes",
            "assets": [win, a]}


def test_the_release_check_takes_the_appimage_not_the_windows_installer(monkeypatch):
    monkeypatch.setattr(updates, "_get", lambda url, *_f: _release_json())
    rel = updates.latest()
    assert (rel.asset_url, rel.sha256, rel.size) == (URL, SHA, len(APPIMAGE))
    assert updates.installer_path(rel).name == "OnionBoard-9.0.0-x86_64.AppImage"


def test_an_appimage_it_cannot_check_is_not_offered(monkeypatch):
    monkeypatch.setattr(updates, "_get", lambda url, *_f: _release_json(digest=None))
    assert updates.latest().asset_url == ""


@pytest.fixture
def running_appimage(tmp_path, monkeypatch):
    """This process as if started from tmp_path/apps/OnionBoard-x86_64.AppImage."""
    apps = tmp_path / "apps"
    apps.mkdir()
    old = apps / "OnionBoard-x86_64.AppImage"
    old.write_bytes(b"\x7fELF old version")
    old.chmod(0o755)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPIMAGE", str(old))
    return old


def test_only_a_copy_started_from_an_appimage_updates_itself(running_appimage, monkeypatch):
    assert updates.can_install() and updates.appimage() == running_appimage
    monkeypatch.setattr(os, "access", lambda p, mode: False)   # a folder it can't write
    assert not updates.can_install()
    monkeypatch.undo()
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert not updates.can_install()                          # a folder build
    monkeypatch.setenv("APPIMAGE", str(running_appimage))
    monkeypatch.delattr(sys, "frozen")
    assert not updates.can_install()                          # from source


def test_install_replaces_the_appimage_and_starts_it_after_this_copy_ends(
        running_appimage, tmp_path, monkeypatch):
    # the "new version" is a script that says it ran, with the environment it got
    ran = tmp_path / "ran.txt"
    new = tmp_path / "download.AppImage"
    new.write_text(f'#!/bin/sh\necho "started $LD_LIBRARY_PATH|$APPDIR" > "{ran}"\n')
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEIxyz")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/opt/mine")
    monkeypatch.setenv("APPDIR", "/tmp/.mount_old")
    old_app = subprocess.Popen(["sleep", "0.5"])   # stands in for this copy
    REAL["start_install"](new, pid=old_app.pid)   # conftest guards the name
    assert running_appimage.read_bytes() == new.read_bytes()
    assert running_appimage.stat().st_mode & 0o111
    assert not list(running_appimage.parent.glob(".*.update"))
    time.sleep(0.2)
    assert not ran.exists()                       # waits while the old copy runs
    old_app.wait()
    deadline = time.monotonic() + 10
    while not ran.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    # the library path PyInstaller's loader set is put back; the old mount is gone
    assert ran.read_text().strip() == "started /opt/mine|"


def test_install_that_cannot_replace_the_file_says_so_and_leaves_it(running_appimage,
                                                                      tmp_path, monkeypatch):
    new = tmp_path / "download.AppImage"
    new.write_bytes(APPIMAGE)
    started = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: started.append(a))

    def refuse(src, dst):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(OSError):
        REAL["start_install"](new)
    assert running_appimage.read_bytes() == b"\x7fELF old version" and started == []
    assert not list(running_appimage.parent.glob(".*.update"))


def test_cleanup_removes_downloaded_appimages():
    updates.UPDATES_DIR.mkdir(parents=True)
    for name in ("OnionBoard-9.0.0-x86_64.AppImage", "OnionBoard-9.0.1-x86_64.AppImage.part",
                 "install.log"):
        (updates.UPDATES_DIR / name).write_bytes(b"x")
    updates.cleanup()
    assert [p.name for p in updates.UPDATES_DIR.iterdir()] == ["install.log"]
