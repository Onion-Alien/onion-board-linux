"""Linux audio devices (soundboard.linux.audio): the sound server's device lists and
streams opened on them through PortAudio's "pulse" (or "pipewire") device. A stand-in pactl and a
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
    monkeypatch.setattr(server, "_pcm", lambda: (7, server.PULSE))
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


def test_without_a_pulse_device_streams_go_through_pipewires_own(server, monkeypatch):
    """Fedora has no "pulse" ALSA device (alsa-plugins-pulseaudio isn't installed),
    only PipeWire's "pipewire": aimed with PIPEWIRE_NODE, named with PIPEWIRE_ALSA."""
    import sounddevice
    from soundboard import engine
    seen = []
    assert server._choose(["HDA Intel PCH: ALC892 Analog (hw:0,0)", "pipewire",
                           "default"]) == (1, "pipewire")
    monkeypatch.setattr(server, "_pcm", lambda: (1, server.PIPEWIRE))
    monkeypatch.setattr(sounddevice, "OutputStream", lambda **k: seen.append(
        (k["device"], os.environ.get("PIPEWIRE_NODE"), os.environ.get("PIPEWIRE_ALSA"),
         os.environ.get("PULSE_SINK"))))
    monkeypatch.setattr(sounddevice, "InputStream", lambda **k: seen.append(
        (k["device"], os.environ.get("PIPEWIRE_NODE"))))
    monkeypatch.delenv("PIPEWIRE_NODE", raising=False)
    engine.sd.OutputStream(device=engine.find_device("output", "Onion Board Cable Input"),
                           samplerate=48000, channels=2)
    engine.sd.InputStream(device=engine.find_device("input", "Blue Yeti Analog Stereo"),
                          samplerate=44100, channels=1)
    (i, node, props, pulse), (j, mic) = seen
    assert (i, node, pulse) == (1, "onionboard_cable", None) and "Onion Board" in props
    assert (j, mic) == (1, "alsa_input.usb-mic")
    assert "PIPEWIRE_NODE" not in os.environ and "PIPEWIRE_ALSA" not in os.environ
    # "pulse" is still the first choice where both are there
    assert server._choose(["pipewire", "pulse"]) == (1, "pulse")
    with pytest.raises(RuntimeError, match="pipewire-alsa"):
        server._choose(["default"])


def test_pulseaudios_null_sink_gets_the_safer_buffer(server, monkeypatch):
    """On PulseAudio the cable is a null sink, which stops asking for sound for about
    2 s after an underrun: at "low" it carried sound in bursts. It opens at "high";
    a sound card, and PipeWire's cable, keep what the user picked."""
    import sounddevice
    from soundboard import engine
    pulse_sinks = (SINKS.replace("\tName: alsa_output", "\tDriver: module-alsa-card.c\n"
                                 "\tName: alsa_output")
                   .replace("\tName: onionboard_cable", "\tDriver: module-null-sink.c\n"
                            "\tName: onionboard_cable"))
    monkeypatch.setattr(server, "_pactl", lambda *a: {
        ("list", "sinks"): pulse_sinks, ("list", "sources"): SOURCES}.get(a, ""))
    server.refresh()
    monkeypatch.setattr(sounddevice, "OutputStream", Recorded)
    monkeypatch.setattr(server, "_pcm", lambda: (7, server.PULSE))
    lat = []
    monkeypatch.setattr(Recorded, "__init__", lambda self, **k: lat.append(k.get("latency")))
    cable = engine.find_device("output", "Onion Board Cable Input")
    speakers = engine.find_device("output", "Built-in Audio Analog Stereo")
    for latency in ("low", 0.01, "high", 0.2):
        engine.sd.OutputStream(device=cable, samplerate=48000, channels=2, latency=latency)
    engine.sd.OutputStream(device=speakers, samplerate=48000, channels=2, latency="low")
    assert lat == ["high", "high", "high", 0.2, "low"]
    monkeypatch.setattr(server, "_pactl", lambda *a: {     # PipeWire: "Driver: PipeWire"
        ("list", "sinks"): SINKS.replace("\tName:", "\tDriver: PipeWire\n\tName:"),
        ("list", "sources"): SOURCES}.get(a, ""))
    server.refresh()
    engine.sd.OutputStream(device=cable, samplerate=48000, channels=2, latency="low")
    assert lat[-1] == "low"


def test_no_sound_server_means_no_devices(monkeypatch):
    from soundboard import engine
    from soundboard.linux import audio
    monkeypatch.setattr(audio, "_pactl", lambda *a: "")
    monkeypatch.setattr(audio, "_devices", None)
    assert engine.list_devices("output") == [] and engine.default_device_name("input") is None
    assert engine.find_device("output", "Anything") is None


def _without(listing: str, name: str) -> str:
    """A `pactl list` answer with one device unplugged."""
    blocks = listing.replace("\nSource #", "\n\0Source #").replace("\nSink #", "\n\0Sink #")
    return "".join(b for b in blocks.split("\0") if f"Name: {name}\n" not in b)


def test_a_device_thats_gone_is_never_opened(server, monkeypatch):
    """The lists were read while it was there; opening it now would land the stream on
    the server's default device (the speakers) instead."""
    from soundboard import engine
    monkeypatch.setattr(server, "_pactl", lambda *a: {
        ("list", "sinks"): _without(SINKS, "onionboard_cable"),
        ("list", "sources"): SOURCES}.get(a, ""))
    cable = engine.find_device("output", "Onion Board Cable Input")   # still listed
    with pytest.raises(RuntimeError, match="device not found: Onion Board Cable Input"):
        engine.sd.OutputStream(device=cable, samplerate=48000, channels=2)


def test_a_new_stream_gets_time_to_start(server, monkeypatch):
    """PulseAudio gives a new stream on a null sink (the cable) a few callbacks and
    then none for up to 2 s: the watchdog reopened it at 1.5 s, which started the
    wait over, so the cable never carried a sound. A stream still silent after its
    start-up time is reopened as before."""
    import time
    from soundboard import engine
    from soundboard.linux import engine as linux_engine
    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(linux_engine, "GONE_POLL_S", 1e9)
    e = engine.Engine()
    try:
        e.set_main_device("Onion Board Cable Input")
        first = e.main_stream
        assert first is not None and not e.errors
        e._last_cb["main"] = clock[0]          # its first few callbacks, then quiet
        for _ in range(int(linux_engine.START_S / 0.5) - 1):
            clock[0] += 0.5
            e.check_streams()
        assert e.main_stream is first and e.stalls == 0
        e._last_cb["main"] = clock[0]          # it got going
        clock[0] += 1.0
        e.check_streams()
        assert e.main_stream is first and e.stalls == 0
        clock[0] += engine.STALL_S + 0.5       # then really stopped: reopened
        e.check_streams()
        assert e.stalls == 1 and e.main_stream is not first
        again = e.main_stream                  # and the reopened one gets its time too
        clock[0] += linux_engine.START_S - 0.5
        e.check_streams()
        assert e.stalls == 1 and e.main_stream is again
    finally:
        e.shutdown()


def test_an_unplugged_device_is_let_go_and_taken_back_when_it_returns(server, monkeypatch):
    """The sound server moves an unplugged device's stream to its default device and
    it plays on: the watchdog closes it, says the device is gone, and reopens it on
    that device once it's back."""
    import time
    from soundboard import engine
    from soundboard.linux import engine as linux_engine
    answers = {("list", "sinks"): SINKS, ("list", "sources"): SOURCES, ("info",): INFO}
    monkeypatch.setattr(server, "_pactl", lambda *a: answers.get(a, ""))
    monkeypatch.setattr(linux_engine, "GONE_POLL_S", 0)
    e = engine.Engine()
    try:
        e.set_mon_device("Onion Board Cable Input")
        e.set_main_device("Built-in Audio Analog Stereo")
        assert e.mon_stream is not None and e.main_stream is not None and not e.errors

        def watch(until):
            deadline = time.monotonic() + 5
            while not until() and time.monotonic() < deadline:
                e._last_cb.update(dict.fromkeys(e._last_cb, time.monotonic()))  # not stalled
                e.check_streams()
                time.sleep(0.02)
            return until()
        assert not watch(lambda: e.mon_stream is None)            # there: left alone
        answers[("list", "sinks")] = _without(SINKS, "onionboard_cable")
        assert watch(lambda: e.mon_stream is None)
        assert e.errors["mon"] == "device not found: Onion Board Cable Input"
        assert e.main_stream is not None and "main" not in e.errors   # the others stay
        answers[("list", "sinks")] = SINKS                        # plugged back in
        e._last_try["mon"] = time.monotonic() - engine.RETRY_S - 1
        assert watch(lambda: e.mon_stream is not None) and "mon" not in e.errors
    finally:
        e.shutdown()


BLUETOOTH = """Source #80
\tName: bluez_input.AA_BB_CC_DD_EE_FF.0
\tDescription: WH-1000XM4
\tSample Specification: s16le 1ch 16000Hz
\tMonitor of Sink: n/a
"""


def test_a_bluetooth_headsets_mic_gets_the_call_quality_warning(server, monkeypatch):
    # Linux doesn't call it "Hands-Free": the sound server's name says Bluetooth
    from soundboard.linux import wording
    from soundboard.ui import mainwindow
    answers = {("list", "sinks"): SINKS, ("list", "sources"): SOURCES + BLUETOOTH,
               ("info",): INFO}
    monkeypatch.setattr(server, "_pactl", lambda *a: answers.get(a, ""))
    server.refresh()
    assert mainwindow.is_hands_free("WH-1000XM4")
    assert not mainwindow.is_hands_free("Blue Yeti Analog Stereo")
    assert mainwindow.is_hands_free("Headset (WH-1000XM4 Hands-Free AG Audio)")  # upstream's
    said = wording.linux("That's a Bluetooth headset's phone-call mic: while it's open, "
                         "Windows switches the headset to call quality, so everything")
    assert "Windows" not in said and "the headset switches to call quality" in said
