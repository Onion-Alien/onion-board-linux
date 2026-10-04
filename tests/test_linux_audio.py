"""Linux audio devices (soundboard.linux.audio): the sound server's device lists and
streams opened on them through PortAudio's "pulse" device. A stand-in pactl and a
stream class that records what it was opened with: no sound server, no sound."""
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux only")

SINKS = """Sink #47
\tState: SUSPENDED
\tName: alsa_output.pci-0000_00_1f.3.analog-stereo
\tDescription: Built-in Audio Analog Stereo
\tSample Specification: s32le 2ch 48000Hz
Sink #64
\tName: onionboard_cable
\tDescription: Onion Board Cable Input
\tSample Specification: float32le 2ch 48000Hz
Sink #70
\tName: usb_headset
\tDescription: Built-in Audio Analog Stereo
\tSample Specification: s16le 2ch 44100Hz
"""
SOURCES = """Source #48
\tName: alsa_output.pci-0000_00_1f.3.analog-stereo.monitor
\tDescription: Monitor of Built-in Audio Analog Stereo
\tSample Specification: s32le 2ch 48000Hz
\tMonitor of Sink: alsa_output.pci-0000_00_1f.3.analog-stereo
Source #49
\tName: alsa_input.usb-mic
\tDescription: Blue Yeti Analog Stereo
\tSample Specification: s16le 1ch 44100Hz
\tMonitor of Sink: n/a
Source #65
\tName: onionboard_cable_out
\tDescription: Onion Board Cable Output
\tSample Specification: float32le 2ch 48000Hz
\tMonitor of Sink: n/a
"""
INFO = """Server Name: PulseAudio (on PipeWire 1.0.5)
Default Sink: alsa_output.pci-0000_00_1f.3.analog-stereo
Default Source: alsa_input.usb-mic
"""


@pytest.fixture
def server(monkeypatch):
    from soundboard.linux import audio
    answers = {("list", "sinks"): SINKS, ("list", "sources"): SOURCES, ("info",): INFO}
    monkeypatch.setattr(audio, "_pactl", lambda *a: answers.get(a, ""))
    monkeypatch.setattr(audio, "_devices", None)
    audio.refresh()
    return audio


def test_parse_list_reads_names_rates_and_monitors():
    from soundboard.linux import audio
    got = audio.parse_list(SOURCES)
    assert [d["name"] for d in got] == ["alsa_output.pci-0000_00_1f.3.analog-stereo.monitor",
                                        "alsa_input.usb-mic", "onionboard_cable_out"]
    assert got[0]["monitor_of"] and not got[1]["monitor_of"]
    assert (got[1]["rate"], got[1]["channels"]) == (44100, 1)


def test_lists_defaults_and_names(server):
    from soundboard import engine
    outs = [d["name"] for d in engine.list_devices("output")]
    ins = [d["name"] for d in engine.list_devices("input")]
    # two devices with one description are told apart; monitors aren't mics
    assert outs == ["Built-in Audio Analog Stereo", "Onion Board Cable Input",
                    "Built-in Audio Analog Stereo (2)"]
    assert ins == ["Blue Yeti Analog Stereo", "Onion Board Cable Output"]
    assert engine.default_device_name("output") == "Built-in Audio Analog Stereo"
    assert engine.default_device_name("input") == "Blue Yeti Analog Stereo"
    i = engine.find_device("output", "Onion Board Cable Input")
    assert i >= server.FIRST_INDEX and engine.list_name(i) == "Onion Board Cable Input"
    # the cable is found the way VB-Cable is
    assert engine.virtual_outputs() == ["Onion Board Cable Input"]
    assert engine.virtual_mic_for("Onion Board Cable Input") == "Onion Board Cable Output"


def test_query_devices_answers_for_the_stand_in_indices(server):
    from soundboard import engine
    from soundboard.ui import mainwindow
    assert engine.sd is mainwindow.sd is server.sd
    i = engine.find_device("input", "Blue Yeti Analog Stereo")
    d = engine.sd.query_devices(i)
    assert d["default_samplerate"] == 44100.0 and d["max_input_channels"] == 1
    assert d["max_output_channels"] == 0


class Recorded:
    """A stream class that records the device and environment it was opened with."""
    opened: list = []

    def __init__(self, **kw):
        Recorded.opened.append((kw.get("device"), os.environ.get("PULSE_SINK"),
                                os.environ.get("PULSE_SOURCE"),
                                os.environ.get("PULSE_PROP_OVERRIDE")))


def test_a_stream_opens_on_pulse_aimed_at_its_device(server, monkeypatch):
    import sounddevice
    from soundboard import engine
    sd = engine.sd
    monkeypatch.setattr(sounddevice, "OutputStream", Recorded)   # looked up at each call
    monkeypatch.setattr(sounddevice, "InputStream", Recorded)
    monkeypatch.setattr(server, "_pcm_index", lambda: 7)
    Recorded.opened = []
    monkeypatch.delenv("PULSE_SINK", raising=False)
    cable = engine.find_device("output", "Onion Board Cable Input")
    mic = engine.find_device("input", "Blue Yeti Analog Stereo")
    sd.OutputStream(device=cable, samplerate=48000, channels=2)
    sd.InputStream(device=mic, samplerate=44100, channels=1)
    sd.OutputStream(device=3, samplerate=48000, channels=2)   # a real index: untouched
    (d1, sink1, _s, prop), (d2, _k, src2, _p), (d3, sink3, _s3, _p3) = Recorded.opened
    assert (d1, sink1) == (7, "onionboard_cable") and "Onion Board" in prop
    assert (d2, src2) == (7, "alsa_input.usb-mic")
    assert (d3, sink3) == (3, None)
    assert "PULSE_SINK" not in os.environ and "PULSE_PROP_OVERRIDE" not in os.environ


def test_no_sound_server_means_no_devices(monkeypatch):
    from soundboard import engine
    from soundboard.linux import audio
    monkeypatch.setattr(audio, "_pactl", lambda *a: "")
    monkeypatch.setattr(audio, "_devices", None)
    assert engine.list_devices("output") == [] and engine.default_device_name("input") is None
    assert engine.find_device("output", "Anything") is None
