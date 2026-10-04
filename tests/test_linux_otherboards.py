"""Import from another soundboard on Linux: Windows paths in boards, boards in Wine /
Proton prefixes, Soundux for Linux's config and X key codes, EXP Soundboard's Java
preferences file."""
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux only")


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("APPDATA", str(h / ".local" / "share"))
    monkeypatch.delenv("WINEPREFIX", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return h


def _sound(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"RIFF")   # only looked at, never decoded here
    return p


def _source(key):
    from soundboard import otherboards
    return otherboards.by_key(key)


def test_local_path(tmp_path):
    from soundboard.linux.wine import local_path
    pfx = tmp_path / "pfx"
    (pfx / "drive_c").mkdir(parents=True)
    assert local_path("Z:\\srv\\sfx\\a.mp3", pfx) == "/srv/sfx/a.mp3"
    assert local_path("C:\\Sounds\\a.mp3", pfx) == str(pfx / "drive_c" / "Sounds" / "a.mp3")
    (pfx / "dosdevices").mkdir()
    (pfx / "dosdevices" / "d:").symlink_to(tmp_path / "disk")
    assert local_path("d:\\x\\b.wav", pfx) == str(pfx / "dosdevices" / "d:" / "x" / "b.wav")
    assert local_path("/base/sub\\vine boom.wav") == "/base/sub/vine boom.wav"


def test_a_windows_path_gets_its_file_name_even_when_its_file_isnt_here(tmp_path):
    from soundboard import expboard
    p = tmp_path / "b.json"
    p.write_text(json.dumps({"soundboardEntries": [
        {"file": "D:\\Sounds\\airhorn.mp3", "activationKeysNumbers": [17, 49]}]}))
    [e] = expboard.read(p)
    assert (e.name, e.hotkey, e.exists) == ("airhorn", "ctrl+1", False)


def test_a_linux_file_with_a_backslash_is_left_alone(tmp_path):
    from soundboard.otherboards import Entry
    f = _sound(tmp_path / "a\\b.wav")
    e = Entry(str(f), "a\\b", exists=True)
    assert (e.path, e.name) == (str(f), "a\\b")


def test_soundpad_under_proton_found_and_its_c_drive_read(home):
    """Soundpad in a Proton prefix: its list is found there and C:\\ paths are that
    prefix's drive_c; Z:\\ is the Linux file system."""
    pfx = home / ".local" / "share" / "Steam" / "steamapps" / "compatdata" / "629520" / "pfx"
    music = _sound(pfx / "drive_c" / "Sounds" / "bruh.wav")
    native = _sound(home / "sfx" / "boom.wav")
    spl = pfx / "drive_c" / "users" / "steamuser" / "AppData" / "Roaming" / "Leppsoft" \
        / "soundlist.spl"
    spl.parent.mkdir(parents=True)
    spl.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<Soundlist rel="C:\\Sounds">
  <Sound url="bruh.wav" title="" key="49" keyModifiers="2"/>
  <Sound url="Z:{str(native).replace('/', chr(92))}" title="Boom"/>
  <Sound url="C:\\gone\\nope.mp3" title=""/>
</Soundlist>""", encoding="utf-8")
    src = _source("soundpad")
    assert src.find() == spl
    rows = src.read(spl)
    assert [(e.name, e.exists) for e in rows] == [("bruh", True), ("Boom", True),
                                                  ("nope", False)]
    assert [Path(e.path) for e in rows[:2]] == [music, native]
    assert rows[0].hotkey == "ctrl+1"


def test_nothing_found_without_a_board(home):
    for key in ("soundpad", "resanance", "soundux", "expboard"):
        assert _source(key).find() is None


def test_resanance_in_wine_is_found(home):
    db = home / ".wine" / "drive_c" / "users" / "me" / "AppData" / "Roaming" / "Resanance" \
        / "data" / "Resanance.db"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"x")
    assert _source("resanance").find() == db


def _soundux(path: Path, sounds: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"data": {"soundIdCounter": 9, "tabs": [
        {"id": 1, "name": "Memes", "path": str(path.parent), "sounds": sounds}]}}))
    return path


def test_soundux_for_linux_reads_x_key_codes(home):
    """Soundux for Linux's config: found in ~/.config, its hotkeys are X key codes
    (37 left Ctrl, 10 the 1 key, 67 F1, 50 left Shift; below 8, mouse buttons)."""
    a, b = _sound(home / "sfx" / "a.wav"), _sound(home / "sfx" / "b.wav")
    cfg = _soundux(home / ".config" / "Soundux" / "config.json", [
        {"name": "a", "path": str(a), "hotkeys": [37, 10]},
        {"name": "b", "path": str(b), "hotkeys": [{"key": 50, "type": 0}, {"key": 67}]},
        {"name": "c", "path": str(a), "hotkeys": [3]},
        {"name": "d", "path": str(a), "hotkeys": [37, 255]}])
    src = _source("soundux")
    assert src.find() == cfg
    assert [e.hotkey for e in src.read(cfg)] == ["ctrl+1", "shift+f1", "", ""]


def test_soundux_flatpak_config_is_found(home):
    cfg = _soundux(home / ".var" / "app" / "io.github.Soundux" / "config" / "Soundux"
                   / "config.json", [])
    assert _source("soundux").find() == cfg


def test_soundux_config_from_windows_keeps_windows_key_codes(home, tmp_path):
    """One copied over from Windows (its paths are Windows ones) has Windows codes."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"data": {"soundIdCounter": 2, "tabs": [{"name": "T", "sounds": [
        {"name": "a", "path": "C:\\Sounds\\a.mp3", "hotkeys": [162, 49]}]}]}}))
    [e] = _source("soundux").read(cfg)
    assert (e.name, e.hotkey, e.exists) == ("a", "ctrl+1", False)


def test_exp_board_from_javas_preferences_file(home):
    from soundboard import expboard
    board = home / "boards" / "mine.json"
    board.parent.mkdir()
    board.write_text(json.dumps({"soundboardEntries": []}))
    prefs = home / ".java" / ".userPrefs" / "Expenosa's Soundboard" / "prefs.xml"
    prefs.parent.mkdir(parents=True)
    prefs.write_text(f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE map SYSTEM "http://java.sun.com/dtd/preferences.dtd">
<map MAP_XML_VERSION="1.0">
  <entry key="lastSoundboardUsed" value="{board}"/>
</map>""", encoding="utf-8")
    assert expboard.default_board() == board
    board.unlink()
    assert expboard.default_board() is None
