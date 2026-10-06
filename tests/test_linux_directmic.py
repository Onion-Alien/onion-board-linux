"""Linux: "Straight into my mic" (soundboard/linux/directmic.py). Onion Board makes a
mic of its own ("Onion Board Mic": a null sink the engine plays into + a source
remapped from its monitor) and makes it the default input; the user's mic comes back
as the default on a quit, on another route, and when the app dies (a holder shell).
The sound server is a stand-in pactl; the holder runs for real on a fake pactl."""
import json
import os
import subprocess
import sys
import time

import pytest
from platform_hooks import REAL
from test_linux_ui import server, window  # noqa: F401 - fixtures

from soundboard import directmic, library, updates
from soundboard.linux import audio
from soundboard.linux import directmic as ldm

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux only")

USER_MIC = "alsa_input.usb-headset.mono"


class Server:
    """Just enough of pactl: sinks, sources, modules and the default source."""

    def __init__(self):
        self.sinks = {"alsa_output.speakers": "Speakers"}
        self.sources = {USER_MIC: "Headset Mic", "alsa_output.speakers.monitor": "Monitor"}
        self.modules: dict[str, str] = {}
        self.default = USER_MIC
        self.calls: list[tuple] = []
        self._next = 20

    def __call__(self, *args):
        self.calls.append(args)
        out, code = "", 0
        if args == ("info",):
            out = f"Server Name: PulseAudio (on PipeWire 1.6.2)\nDefault Source: {self.default}\n"
        elif args[:2] == ("list", "short"):
            if args[2] == "modules":
                out = "".join(f"{i}\tmodule-x\t{a}\t\n" for i, a in self.modules.items())
            else:
                names = self.sinks if args[2] == "sinks" else self.sources
                out = "".join(f"{i}\t{n}\tmodule\tfloat32le 2ch 48000Hz\tIDLE\n"
                              for i, n in enumerate(names))
        elif args[0] == "load-module":
            kv = dict(a.split("=", 1) for a in args[2:] if "=" in a)
            mid = str(self._next)
            self._next += 1
            self.modules[mid] = " ".join(args[2:])
            if args[1] == "module-null-sink":
                self.sinks[kv["sink_name"]] = ldm.SINK_DESC
                self.sources[kv["sink_name"] + ".monitor"] = "Monitor of " + ldm.SINK_DESC
            else:
                self.sources[kv["source_name"]] = ldm.SOURCE_DESC
            out = mid + "\n"
        elif args[0] == "unload-module":
            a = self.modules.pop(args[1], "")
            for n in list(self.sinks):
                if f"sink_name={n}" in a:
                    del self.sinks[n]
                    self.sources.pop(n + ".monitor", None)
            for n in list(self.sources):
                if f"source_name={n}" in a:
                    del self.sources[n]
                    if self.default == n:   # what PipeWire / module-rescue-streams do
                        self.default = USER_MIC
        elif args[0] == "set-default-source":
            self.default = args[1]
        return subprocess.CompletedProcess(args, code, out, "")


@pytest.fixture
def pa(monkeypatch):
    s = Server()
    monkeypatch.setattr(ldm, "_pactl", s)
    monkeypatch.setattr(ldm, "_have_pactl", lambda: True)   # (CI runners have no pactl)
    monkeypatch.setattr(ldm, "_holder", None)
    held = []
    monkeypatch.setattr(ldm, "_hold", lambda mods: held.append(list(mods)))
    monkeypatch.setattr(ldm, "_seen", {"at": None, "busy": False, "there": False,
                                       "default": ""})
    s.held = held
    directmic.forget_status()
    yield s
    directmic.forget_status()


def test_one_click_makes_the_mic_and_makes_it_the_default(pa):
    assert directmic.status() == "missing"
    assert directmic.install(None) is None
    assert pa.default == ldm.SOURCE and ldm.exists()
    assert ldm.user_mic() == USER_MIC          # kept, to put back
    assert pa.held and len(pa.held[-1]) == 2   # the holder knows both modules
    directmic.forget_status()
    assert directmic.status() == "ready" and directmic.works(directmic.status())
    assert directmic.ensure() and len(pa.modules) == 2   # never made twice


def test_another_default_mic_is_other_and_one_click_takes_it_back(pa):
    directmic.install(None)
    pa.default = "alsa_input.webcam"           # picked in the system's Sound settings
    directmic.forget_status()
    assert directmic.status() == "other" and not directmic.works("other")
    assert directmic.install(None) is None and pa.default == ldm.SOURCE
    assert ldm.user_mic() == "alsa_input.webcam"   # the one to put back now


def test_set_up_but_not_there_is_ready_and_the_engine_makes_it(pa):
    """It goes with every quit: the next start is ready, made as the engine opens it."""
    directmic.install(None)
    ldm.release()
    assert pa.default == USER_MIC and not pa.modules
    directmic.forget_status()
    assert directmic.status() == "ready"
    directmic.uninstall()
    directmic.forget_status()
    assert directmic.status() == "missing" and not directmic.anything_installed()


def test_release_puts_the_users_mic_back_and_takes_the_mic_away(pa):
    directmic.install(None)
    ldm.release()
    assert pa.default == USER_MIC and not pa.modules and not ldm.exists()
    ldm.release()                               # nothing there: nothing to do
    assert directmic.cli(["remove"]) == 0 and not directmic.anything_installed()
    assert directmic.cli(["install", "{a}"]) == 2


def test_the_mic_is_hidden_from_every_device_list(pa, monkeypatch):
    directmic.install(None)
    monkeypatch.setattr(audio, "_devices", [
        audio.Device(100_000, "output", "alsa_output.speakers", "Speakers", 48000, 2),
        audio.Device(100_001, "output", ldm.SINK, ldm.SINK_DESC, 48000, 2),
        audio.Device(100_002, "input", USER_MIC, "Headset Mic", 48000, 1),
        audio.Device(100_003, "input", ldm.SOURCE, ldm.SOURCE_DESC, 48000, 2)])
    names = [d["name"] for k in ("input", "output") for d in audio.list_devices(k)]
    assert names == ["Headset Mic", "Speakers"]
    with audio.showing_hidden():
        assert ldm.SINK_DESC in [d["name"] for d in audio.list_devices("output")]
    assert audio.own_mic().pulse == USER_MIC


def test_the_board_never_records_its_own_mic(pa, monkeypatch):
    """"The default mic" while Onion Board's is the default: the user's own."""
    directmic.install(None)
    monkeypatch.setattr(audio, "_devices", [
        audio.Device(100_002, "input", USER_MIC, "Headset Mic", 48000, 1),
        audio.Device(100_003, "input", ldm.SOURCE, ldm.SOURCE_DESC, 48000, 2)])
    monkeypatch.setattr(audio, "present", lambda: None)
    seen = {}

    class Stream:
        def __init__(self, **kw):
            seen.update(kw, source=os.environ.get("PULSE_SOURCE"))
    audio._open("input", Stream, {"device": None})
    assert seen["source"] == USER_MIC and seen["device"] == 0


def test_the_default_mic_is_pinned_so_it_never_follows_onto_ours(pa, monkeypatch):
    """Opened while the user's mic is the default (before Onion Board's mic is made):
    aimed at that mic by name, not left on "default", which the sound server moves
    onto Onion Board's mic as it becomes the default (found on Fedora)."""
    monkeypatch.setattr(audio, "_devices", [
        audio.Device(100_002, "input", USER_MIC, "Headset Mic", 48000, 1)])
    monkeypatch.setattr(audio, "present", lambda: None)
    seen = {}

    class Stream:
        def __init__(self, **kw):
            seen.update(kw, source=os.environ.get("PULSE_SOURCE"))
    audio._open("input", Stream, {"device": None})
    assert seen["source"] == USER_MIC and seen["device"] == 0


def test_the_engine_sends_into_the_mic_as_an_output(pa, monkeypatch):
    from soundboard import engine
    directmic.install(None)
    devs = [audio.Device(100_000, "output", "alsa_output.speakers", "Speakers", 48000, 2),
            audio.Device(100_001, "output", ldm.SINK, ldm.SINK_DESC, 48000, 2)]
    monkeypatch.setattr(audio, "refresh", lambda: devs)
    monkeypatch.setattr(audio, "_devices", devs)
    monkeypatch.setattr(audio, "present", lambda: None)
    e = engine.Engine()
    try:
        e.set_main_device(directmic.DEVICE)
        assert e.main_stream is not None and e.names["main"] == directmic.DEVICE
        assert not e.main_direct            # the board's mic is its own stream, as ever
        assert "main" not in e.errors
    finally:
        e.shutdown()


def test_routes_and_first_start_follow_windows(app_dir):
    assert "mic" in library.ROUTES
    assert library.Config.first_start().route == "mic"   # one click away, as on Windows


def test_the_window_offers_the_mic_and_gives_the_users_mic_back(window, pa):  # noqa: F811
    from soundboard.ui import mainwindow
    w, toasts = window
    assert "mic" in [k for _t, k in mainwindow.ROUTE_CHOICES]
    directmic.install(None)
    w.cfg.route = "mic"
    w.open_windows_mic()                        # "game has no mic setting": ours already
    assert pa.default == ldm.SOURCE and "Onion Board Mic" in toasts[-1][1]
    w.set_route("cable")
    assert pa.default == USER_MIC and not pa.modules
    directmic.ensure()
    w.shutdown()
    assert pa.default == USER_MIC and not pa.modules


@pytest.fixture
def fake_pactl(tmp_path, monkeypatch):
    """A pactl on PATH that logs its calls and says Onion Board's mic is the default."""
    log = tmp_path / "pactl.log"
    exe = tmp_path / "bin" / "pactl"
    exe.parent.mkdir()
    exe.write_text(f'#!/bin/sh\necho "$@" >> {log}\n'
                   f'[ "$1" = info ] && echo "Default Source: {ldm.SOURCE}"\nexit 0\n')
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{exe.parent}:{os.environ['PATH']}")
    return log


def _wait_for(path, text, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists() and text in path.read_text():
            return True
        time.sleep(0.02)
    return False


@pytest.mark.parametrize("signal_first", [False, True])
def test_the_holder_puts_things_back_however_the_app_ends(fake_pactl, monkeypatch, tmp_path,
                                                          signal_first):
    """The app's end of the holder's pipe closing (a quit, a crash, kill -9) is its cue;
    the signals a terminal sends the app's group (Ctrl+C) don't stop it first."""
    import signal
    monkeypatch.setattr(ldm, "user_mic", lambda: USER_MIC)
    REAL["directmic_hold_fn"](["31", "32"])
    p = ldm._holder
    try:
        assert p is not None and p.poll() is None
        time.sleep(0.2)   # (the shell set its traps)
        if signal_first:
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                os.killpg(p.pid, sig)
            time.sleep(0.2)
            assert p.poll() is None and not fake_pactl.exists()
        p.stdin.close()                         # what the app dying does to it
        assert _wait_for(fake_pactl, "unload-module 32")
        calls = fake_pactl.read_text().splitlines()
        assert calls == ["info", f"set-default-source {USER_MIC}",
                         "unload-module 31", "unload-module 32"]
        p.wait(5)
    finally:
        if p.poll() is None:
            p.kill()
        monkeypatch.setattr(ldm, "_holder", None)


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


def test_made_as_the_engine_opens_it_it_takes_the_default(pa, monkeypatch):
    """Set up, then a quit took it away: the next start makes it and it's the default
    again (found on Fedora: it was made, but Default stayed on the real mic)."""
    from soundboard import engine
    directmic.install(None)
    ldm.release()
    assert pa.default == USER_MIC
    devs = [audio.Device(100_001, "output", ldm.SINK, ldm.SINK_DESC, 48000, 2)]
    monkeypatch.setattr(audio, "refresh", lambda: devs)
    monkeypatch.setattr(audio, "_devices", devs)
    monkeypatch.setattr(audio, "present", lambda: None)
    e = engine.Engine()
    try:
        e.set_main_device(directmic.DEVICE)
        assert e.main_stream is not None and pa.default == ldm.SOURCE
        pa.default = "alsa_input.webcam"        # picked by the user meanwhile
        e.set_main_device(directmic.DEVICE)     # reopened (a stall): there, so it stays
        assert pa.default == "alsa_input.webcam"
    finally:
        e.shutdown()


def test_the_boards_mic_is_reopened_once_ours_is_the_default(pa, monkeypatch):
    """WirePlumber moves a stream aimed at the default along when the default changes
    (follow-default-target): the board's mic, opened on the user's mic while that was
    the default, followed onto Onion Board's on Fedora. It's opened again after the
    switch, aimed at the user's mic, which isn't the default any more."""
    from soundboard import engine
    devs = [audio.Device(100_001, "output", ldm.SINK, ldm.SINK_DESC, 48000, 2),
            audio.Device(100_002, "input", USER_MIC, "Headset Mic", 48000, 1)]
    monkeypatch.setattr(audio, "refresh", lambda: devs)
    monkeypatch.setattr(audio, "_devices", devs)
    monkeypatch.setattr(audio, "present", lambda: None)
    import sounddevice

    class Mic:   # no real capture device in a test
        def __init__(self, **kw):
            pass
        start = stop = close = lambda self: None
    monkeypatch.setattr(sounddevice, "InputStream", Mic)
    aimed = []
    real_set_mic = engine.Engine.set_mic_device

    def spy(self, name):
        aimed.append(pa.default)   # what the default was as the mic opened
        return real_set_mic(self, name)
    monkeypatch.setattr(engine.Engine, "set_mic_device", spy)
    directmic.install(None)
    ldm.release()                               # a fresh start: the user's mic is default
    e = engine.Engine()
    try:
        e.set_mic_device("Headset Mic")   # the user's mic, the default now
        assert aimed == [USER_MIC]
        e.set_main_device(directmic.DEVICE)
        assert pa.default == ldm.SOURCE and aimed == [USER_MIC, ldm.SOURCE]
        assert e.mic_stream is not None
    finally:
        e.shutdown()
