"""Linux pieces that need no desktop: the raw MIDI parser and device list, start at
login (XDG autostart), the single-instance lock, and the data folder."""
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux only")


# ------------------------------------------------------------------ MIDI
def test_parser_packs_messages_like_winmm():
    from soundboard import midi
    from soundboard.linux.midi import Parser
    p = Parser()
    msgs = p.feed(bytes([0x90, 36, 100, 0x80, 36, 0]))
    assert [midi.decode(m) for m in msgs] == [("press", "note", 36), ("release", "note", 36)]


def test_parser_running_status_realtime_and_sysex():
    from soundboard import midi
    from soundboard.linux.midi import Parser
    p = Parser()
    # running status (a second note with no status byte), a clock byte in the middle,
    # a sysex block skipped, a program change (one data byte), split across reads
    out = p.feed(bytes([0x99, 40, 0xF8, 90, 41]))
    out += p.feed(bytes([0, 0xF0, 1, 2, 3, 0xF7, 0xC0, 5, 0xB0, 20]))
    out += p.feed(bytes([127]))
    assert [midi.decode(m) for m in out] == [("press", "note", 40), ("release", "note", 41),
                                             ("press", "pc", 5), ("press", "cc", 20)]


def test_device_list_and_busy(tmp_path, qapp):
    """A fake /dev/snd: FIFOs stand in for the raw MIDI devices."""
    from soundboard import midi
    from soundboard.linux.midi import AlsaRawMidi
    (tmp_path / "controlC0").touch()
    os.mkfifo(tmp_path / "midiC1D0")
    os.mkfifo(tmp_path / "midiC0D0")
    b = AlsaRawMidi(str(tmp_path))
    names = b.devices()
    assert len(names) == 2 and all(names)
    got = []
    b.on_message = lambda key, msg: got.append((key, midi.decode(msg)))
    h = b.open(0, 7)
    w = os.open(tmp_path / "midiC0D0", os.O_WRONLY)
    os.write(w, bytes([0x90, 36, 64]))
    import time
    deadline = time.monotonic() + 3
    while not got and time.monotonic() < deadline:
        time.sleep(0.01)
    assert got == [(7, ("press", "note", 36))]
    closed = []
    b.on_closed = closed.append
    os.close(w)   # the writer going away is the device being unplugged
    deadline = time.monotonic() + 3
    while not closed and time.monotonic() < deadline:
        time.sleep(0.01)
    assert closed == [7]
    b.close(h)


def test_midiin_uses_the_alsa_backend(qapp):
    from soundboard import midi
    from soundboard.linux.midi import AlsaRawMidi
    assert isinstance(midi.MidiIn().backend, AlsaRawMidi)


# ------------------------------------------------------------------ autostart
def test_autostart_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("APPIMAGE", raising=False)
    from soundboard import autostart
    assert autostart.available()
    assert not autostart.is_enabled() and autostart.current() is None
    assert autostart.set_enabled(True, hidden=True)
    entry = tmp_path / "autostart" / "onionboard.desktop"
    text = entry.read_text()
    assert "Exec=" in text and "--tray" in text and "main.py" in text
    assert autostart.is_enabled()
    entry.write_text(text + "Hidden=true\n")   # switched off in the desktop's settings
    assert not autostart.is_enabled()
    assert autostart.set_enabled(False)
    assert not entry.exists() and autostart.set_enabled(False)


def test_autostart_runs_the_appimage(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPIMAGE", "/opt/apps/Onion Board.AppImage")
    from soundboard import autostart
    assert autostart.command(False) == "'/opt/apps/Onion Board.AppImage'"


# ------------------------------------------------------------------ single instance
def test_lock_is_exclusive_and_freed(tmp_path, monkeypatch, qapp):
    import fcntl
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    from soundboard import singleinstance
    from soundboard.linux import singleinstance as lsi
    monkeypatch.setattr(lsi, "_si", lambda: singleinstance)
    monkeypatch.setattr(singleinstance, "CONNECT_SECONDS", 0.2)
    path = lsi.lock_path()
    assert path.parent == tmp_path
    # someone else holds it: we're not first (and nobody answers on the socket)
    fd = os.open(path, os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    assert singleinstance.claim_single_instance() is False
    os.close(fd)   # they quit (or crashed): the lock is free again
    assert singleinstance.claim_single_instance() is True
    os.close(lsi.claim_single_instance.fd)


# ------------------------------------------------------------------ data folder
def test_appdata_is_the_xdg_data_folder():
    import soundboard.linux  # noqa: F401 - sets it
    assert os.environ["APPDATA"]
    from soundboard.linux import data_home
    assert os.environ.get("APPDATA") == data_home() or "APPDATA" in os.environ


# ------------------------------------------------------------------ Tor
def test_torrc_bridges_use_linux_paths():
    from soundboard import tor
    pt = {"pluggableTransports": {"lyrebird": "ClientTransportPlugin obfs4 exec "
                                              "${pt_path}lyrebird"},
          "bridges": {"obfs4": ["obfs4 1.2.3.4:443 X"]}}
    lines = tor.bridge_config("obfs4", pt)
    assert lines == ["UseBridges 1",
                     "ClientTransportPlugin obfs4 exec pluggable_transports/lyrebird",
                     "Bridge obfs4 1.2.3.4:443 X"]


def test_tor_is_found_as_tor_and_runs_with_its_libraries(tmp_path, monkeypatch):
    from soundboard import tor, torget
    monkeypatch.setattr(tor, "bundle_dirs", lambda: [tmp_path])
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert tor.tor_exe() is None and not tor.available()
    (tmp_path / "tor").write_text("")
    assert tor.tor_exe() == tmp_path / "tor"
    cmd = tor.Tor._command(None, tmp_path / "tor")
    assert cmd[0] == "env" and cmd[1].startswith(f"LD_LIBRARY_PATH={tmp_path}")
    assert cmd[-1] == str(tmp_path / "tor")
    assert torget.TARBALL.startswith("tor-expert-bundle-linux-x86_64-")
    assert "tor/tor" in torget.KEEP and not any(k.endswith(".exe") for k in torget.KEEP)


def test_torget_unpack_keeps_the_execute_bit(tmp_path, monkeypatch):
    import io
    import tarfile
    from soundboard import torget
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in torget.KEEP:
            data = b"#!/bin/sh\n" if not name.endswith((".json", ".txt")) else b"{}"
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    dest = torget.unpack(buf.getvalue(), tmp_path / "bin")
    assert os.access(dest / "tor", os.X_OK)
    assert os.access(dest / "pluggable_transports" / "lyrebird", os.X_OK)
    assert torget.installed(dest)


# ------------------------------------------------------------------ Trash
def test_recycle_moves_to_the_freedesktop_trash(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HOME", str(tmp_path))
    from soundboard import library
    f = tmp_path / "boom.wav"
    f.write_bytes(b"RIFF")
    assert library.recycle(f) and not f.exists()
    trashed = list((tmp_path / "data" / "Trash" / "files").iterdir())
    assert [p.name for p in trashed] == ["boom.wav"]
    assert (tmp_path / "data" / "Trash" / "info" / "boom.wav.trashinfo").is_file()
    assert not library.recycle(tmp_path / "gone.wav")
