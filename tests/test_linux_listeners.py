"""Linux: Who's listening. recording_apps reads PipeWire's links from the cable's far
end / Onion Board's mic to the recording streams and names their programs, so
voicesdk.Listeners can pick the sound mode (Discord's, a browser's, a game's). The
cable's graph below is a real pw-dump from Fedora 44 (PipeWire 1.6), trimmed, with a
stand-in "Discord" (a native PipeWire recorder: its process is on its client)."""
import json
import os
import sys

import pytest

from soundboard import appaudio, voicesdk  # noqa: F401 - appaudio first
from soundboard.linux import appaudio as lappaudio

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux only")

CABLE = json.loads(
    "[{\"id\":58,\"type\":\"PipeWire:Interface:Node\",\"info\":{\"props\":{\"media.class\":\"Audio/Sin"
    "k\",\"node.name\":\"alsa_output.pci-0000_00_05.0.analog-stereo\",\"node.description\":\"Buil"
    "t-in Audio Analog Stereo\",\"client.id\":49,\"object.serial\":58}}},{\"id\":59,\"type\":\"Pipe"
    "Wire:Interface:Node\",\"info\":{\"props\":{\"media.class\":\"Audio/Source\",\"node.name\":\"alsa"
    "_input.pci-0000_00_05.0.analog-stereo\",\"node.description\":\"Built-in Audio Analog Ste"
    "reo\",\"client.id\":49,\"object.serial\":59}}},{\"id\":66,\"type\":\"PipeWire:Interface:Node\","
    "\"info\":{\"props\":{\"media.class\":\"Audio/Sink\",\"node.name\":\"onionboard_cable\",\"node.des"
    "cription\":\"Onion Board Cable Input\",\"client.id\":69,\"object.serial\":140}}},{\"id\":82,\""
    "type\":\"PipeWire:Interface:Node\",\"info\":{\"props\":{\"media.class\":\"Audio/Source\",\"node."
    "name\":\"onionboard_cable_out\",\"node.description\":\"Onion Board Cable Output\",\"client.i"
    "d\":75,\"object.serial\":147}}},{\"id\":76,\"type\":\"PipeWire:Interface:Node\",\"info\":{\"prop"
    "s\":{\"media.class\":\"Stream/Input/Audio\",\"node.name\":\"input.onionboard_cable_out\",\"nod"
    "e.description\":\"Onion Board Cable Output\",\"client.id\":75,\"object.serial\":148}}},{\"id"
    "\":81,\"type\":\"PipeWire:Interface:Link\",\"info\":{\"output-node-id\":66,\"input-node-id\":76"
    ",\"state\":\"active\"}},{\"id\":85,\"type\":\"PipeWire:Interface:Link\",\"info\":{\"output-node-i"
    "d\":66,\"input-node-id\":76,\"state\":\"active\"}},{\"id\":77,\"type\":\"PipeWire:Interface:Clie"
    "nt\",\"info\":{\"props\":{\"application.name\":\"Discord\",\"application.process.id\":4343,\"app"
    "lication.process.binary\":\"Discord\",\"pipewire.sec.pid\":4343,\"object.serial\":158}}},{\""
    "id\":86,\"type\":\"PipeWire:Interface:Node\",\"info\":{\"props\":{\"media.class\":\"Stream/Input"
    "/Audio\",\"node.name\":\"Discord\",\"application.name\":\"Discord\",\"client.id\":77,\"object.se"
    "rial\":159}}},{\"id\":87,\"type\":\"PipeWire:Interface:Link\",\"info\":{\"output-node-id\":82,\""
    "input-node-id\":86,\"state\":\"active\"}},{\"id\":91,\"type\":\"PipeWire:Interface:Link\",\"info"
    "\":{\"output-node-id\":82,\"input-node-id\":86,\"state\":\"active\"}}]")
DISCORD_PID = 4343


def node(i, cls, name, desc="", **props):
    return {"id": i, "type": "PipeWire:Interface:Node",
            "info": {"props": {"media.class": cls, "node.name": name,
                               "node.description": desc, **props}}}


def link(i, out, into):
    return {"id": i, "type": "PipeWire:Interface:Link",
            "info": {"output-node-id": out, "input-node-id": into, "state": "active"}}


@pytest.fixture
def procs(monkeypatch):
    """Made-up processes: pid -> (parent, program path)."""
    table = {DISCORD_PID: (1, "/opt/discord/Discord"),
             4400: (4399, "/opt/discord/Discord"), 4399: (1, "/opt/discord/Discord"),
             5000: (1, "/usr/lib64/firefox/firefox"),
             6000: (1, "/games/Game/Game.exe"),
             7000: (1, "/usr/bin/arecord")}
    monkeypatch.setattr(lappaudio, "process_path", lambda pid: table.get(pid, (0, ""))[1])
    monkeypatch.setattr(lappaudio, "_ppid", lambda pid: table.get(pid, (0, ""))[0])
    from soundboard.linux import voicesdk as lvoicesdk
    monkeypatch.setattr(lvoicesdk, "exe_of", lambda pid: table.get(pid, (0, ""))[1])
    return table


def test_the_program_recording_the_cable_is_found(procs):
    apps = lappaudio.recording_apps("Onion Board Cable Output", dump=CABLE)
    assert [(a.pid, a.exe, a.name) for a in apps] == [(DISCORD_PID, "Discord", "Discord")]
    # the cable's own remap stream (no process) and the real mic's listeners don't count
    assert lappaudio.recording_apps("Built-in Audio Analog Stereo", dump=CABLE) == []
    assert lappaudio.recording_apps("", dump=CABLE) == []


def test_listeners_name_discord_on_the_cable(procs):
    w = voicesdk.Listeners(lister=lambda d: lappaudio.recording_apps(d, dump=CABLE))
    assert w.look("Onion Board Cable Output") == (("discord", "Discord"),)


def mic_route():
    """Straight into my mic: Discord (PulseAudio API, its process on the stream, two
    streams from two of its processes), a browser and a Proton game on Default =
    Onion Board's mic; a recorder pinned to the real mic; the board's own streams."""
    me = os.getpid()
    return [
        node(10, "Audio/Source", "alsa_input.usb", "Blue Yeti Analog Stereo"),
        node(20, "Audio/Source/Virtual", "onionboard_mic", "Onion Board Mic"),
        node(30, "Stream/Input/Audio", "Discord", **{"application.process.id": "4400"}),
        node(31, "Stream/Input/Audio", "Discord", **{"application.process.id": "4399"}),
        node(32, "Stream/Input/Audio", "Firefox", **{"application.process.id": 5000}),
        node(33, "Stream/Input/Audio", "Game.exe", **{"application.process.id": 6000}),
        node(34, "Stream/Input/Audio", "arecord", **{"application.process.id": 7000}),
        node(35, "Stream/Input/Audio", "Onion Board", **{"application.process.id": me}),
        node(36, "Stream/Input/Audio", "Onion Board", **{"application.process.id": me}),
        link(40, 20, 30), link(41, 20, 31), link(42, 20, 32), link(43, 20, 33),
        link(44, 10, 34), link(45, 10, 35), link(46, 20, 36),
    ]


def test_who_records_onion_board_mic(procs):
    apps = {a.exe: a for a in lappaudio.recording_apps("Onion Board Mic", dump=mic_route())}
    assert set(apps) == {"Discord", "firefox", "Game.exe"}   # not the board itself
    assert apps["Discord"].pid == 4399 and apps["Discord"].session_pids == {4399, 4400}
    assert apps["firefox"].path == ""   # the desktop's own program: nothing to scan
    assert apps["Game.exe"].path == "/games/Game/Game.exe"
    # the recorder pinned to the real mic hears the voice alone: not a listener
    assert [a.exe for a in lappaudio.recording_apps("Blue Yeti Analog Stereo",
                                                    dump=mic_route())] == ["arecord"]


def test_listeners_rank_voice_apps_first_and_scan_a_proton_game(procs):
    scanned = []

    def scan(path):
        scanned.append(path)
        return "game"   # a Vivox game
    w = voicesdk.Listeners(lister=lambda d: lappaudio.recording_apps(d, dump=mic_route()),
                           scanner=scan)
    assert w.look("Onion Board Mic") == (("discord", "Discord"), ("webrtc", "Your browser"),
                                         ("game", "Game"))
    assert scanned == ["/games/Game/Game.exe"]


def test_linux_voice_apps_have_their_modes():
    v = voicesdk.VOICE_APPS
    assert v["discord"] == v["vesktop"] == v["discord.exe"] == ("discord", "Discord")
    assert v["firefox"] == v["chromium"] == ("webrtc", "Your browser")
    assert v["mumble"] == ("game", "Mumble")
    assert v["ts3client_linux_amd64"] == ("game", "TeamSpeak")


def test_a_failed_pw_dump_is_no_listeners(monkeypatch):
    import subprocess

    def fail(*a, **k):
        raise FileNotFoundError("pw-dump")
    monkeypatch.setattr(subprocess, "run", fail)
    assert lappaudio.pw_dump() == []
    assert lappaudio.recording_apps("Onion Board Mic") == []


def test_pw_dump_is_decoded_gently(monkeypatch):
    """(one json.loads of a few hundred kB holds Python's lock: the audio waits)"""
    import subprocess
    from soundboard import radio
    calls = []
    real = radio.loads_gently
    monkeypatch.setattr(radio, "loads_gently", lambda s: calls.append(1) or real(s))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 0, stdout=json.dumps(CABLE), stderr=""))
    assert lappaudio.pw_dump() == CABLE and calls == [1]


@pytest.fixture
def window(qapp, app_dir, monkeypatch):
    from PySide6.QtCore import QEvent
    from soundboard.ui import mainwindow
    # both names: soundboard.appaudio star-imports the Linux one, so it holds its own
    # copy (a CI runner has no pw-dump: the real one says no there)
    monkeypatch.setattr(lappaudio, "supported", lambda: (True, ""))
    monkeypatch.setattr(appaudio, "supported", lambda: (True, ""))
    w = mainwindow.MainWindow()
    yield w
    w._load_thread.join(15)
    w.close()
    w.deleteLater()
    qapp.sendPostedEvents(None, QEvent.DeferredDelete)


def test_the_window_watches_who_listens(window):
    assert isinstance(window.listeners, voicesdk.Listeners)
    assert isinstance(window._cable_watch, voicesdk.Listeners)
    assert window._voice_timer.isActive()


def test_straight_into_my_mic_watches_onion_board_mic_not_the_users(window, monkeypatch):
    from soundboard import directmic as dm
    from soundboard import engine as eng
    e = window.engine
    window.cfg.route = "mic"
    window.cfg.mic_device = "Blue Yeti Analog Stereo"
    monkeypatch.setattr(eng, "virtual_outputs", lambda: ["Onion Board Cable Input"])
    monkeypatch.setattr(eng, "virtual_mic_for", lambda o: "Onion Board Cable Output")
    assert window._heard_device() is None   # not sending into it (yet)
    e.names["main"] = dm.DEVICE
    monkeypatch.setattr(e, "main_stream", object())
    assert window._heard_device() == ("Onion Board Mic", "Onion Board Cable Output")
    window.cfg.route = "cable"
    window.cfg.main_device = "Onion Board Cable Input"
    assert window._heard_device() == "Onion Board Cable Output"


def test_the_cable_tip_points_at_default_on_linux(window, monkeypatch):
    toasts = []
    monkeypatch.setattr(window, "toast", lambda text, kind="": toasts.append(text))
    monkeypatch.setattr(window, "_save_now", lambda: None)
    monkeypatch.setattr(window.engine, "tap", object())
    window.engine.tap_name = "Onion Board Cable Input"
    window.cfg.cable_tip_done = False
    monkeypatch.setattr(window._cable_watch, "poll", lambda d: (("discord", "Discord"),))
    window._cable_tip()
    assert toasts and "Default" in toasts[0] and "Onion Board Mic" in toasts[0]
    assert "normal mic" not in toasts[0]
    assert window.cfg.cable_tip_done
