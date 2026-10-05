"""Linux per-program capture (soundboard.linux.appaudio): which PipeWire streams a
capture takes, from a stand-in pw-dump, and the mixing of several streams. No
PipeWire needed (one end-to-end check runs only where pw-record is installed)."""
import os
import sys

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux only")


def node(serial, pid, app, state="running", cls="Stream/Output/Audio"):
    return {"id": serial, "type": "PipeWire:Interface:Node",
            "info": {"state": state, "props": {
                "media.class": cls, "object.serial": serial, "application.name": app,
                "application.process.id": pid, "application.process.binary": app.lower()}}}


# Made-up pids above the kernel's highest (pid_max is at most 4194304), so none is
# this test's own: on WSL a worker can really be pid 1001, and the app leaves itself out
DUMP = [node(10, 9001001, "Firefox"), node(11, 9001002, "Firefox"),   # two tab processes
        node(12, 9002000, "Spotify", state="idle"),
        node(13, 9003000, "Mic", cls="Stream/Input/Audio"),         # a recording: not a player
        {"id": 1, "type": "PipeWire:Interface:Client", "info": {"props": {}}}]


@pytest.fixture
def procs(monkeypatch):
    """A process table: Firefox 9001000 with tabs 9001001/9001002, Spotify 9002000, us."""
    from soundboard.linux import appaudio as la
    me = os.getpid()
    parents = {9001001: 9001000, 9001002: 9001000, 9001000: 1, 9002000: 1, me: 1}
    exes = {9001000: "/usr/lib/firefox/firefox", 9001001: "/usr/lib/firefox/firefox",
            9001002: "/usr/lib/firefox/firefox", 9002000: "/opt/spotify/spotify"}
    monkeypatch.setattr(la, "_ppid", lambda pid: parents.get(pid, 0))
    monkeypatch.setattr(la, "process_path", lambda pid: exes.get(pid, ""))
    monkeypatch.setattr(la, "stream_nodes", lambda dump=None, real=la.stream_nodes:
                        real(DUMP if dump is None else dump))
    return la


def test_stream_nodes_are_players_only():
    from soundboard.linux import appaudio as la
    got = la.stream_nodes(DUMP)
    assert [(n["serial"], n["pid"], n["state"]) for n in got] == [
        ("10", 9001001, "running"), ("11", 9001002, "running"), ("12", 9002000, "idle")]


def test_list_apps_groups_a_program_and_leaves_us_out(procs, monkeypatch):
    from soundboard import appaudio
    apps = appaudio.list_apps()
    assert [(a.pid, a.name, a.active) for a in apps] == [(9001000, "Firefox", True),
                                                         (9002000, "Spotify", False)]
    assert apps[0].session_pids == {9001001, 9001002}


def test_a_capture_takes_its_programs_streams(procs):
    from soundboard import appaudio
    assert appaudio.AppCapture(9001000, None)._wanted() == {"10", "11"}
    assert appaudio.AppCapture(9002000, None)._wanted() == {"12"}
    # everything but Firefox (instant replay passes its own pid this way)
    assert appaudio.AppCapture(9001000, None, include_tree=False)._wanted() == {"12"}
    assert appaudio.AppCapture(os.getpid(), None, include_tree=False)._wanted() == \
        {"10", "11", "12"}


def test_reader_primes_pads_and_drops_what_runs_ahead():
    from soundboard.linux import appaudio as la
    r = la._Reader.__new__(la._Reader)   # no pw-record: just its buffer
    import threading
    from collections import deque
    r.buf, r.frames, r.primed, r.lock = deque(), 0, False, threading.Lock()
    r.buf.append(np.ones((la.PREBUFFER - 1, 2), np.float32))
    r.frames = la.PREBUFFER - 1
    assert r.take(10) is None                       # still priming
    r.buf.append(np.ones((10, 2), np.float32))
    r.frames += 10
    out = r.take(la.PREBUFFER + 50)                 # primed; short by 41: padded
    assert out.shape == (la.PREBUFFER + 50, 2) and out[:la.PREBUFFER + 9].all()
    assert not out[la.PREBUFFER + 9:].any() and r.frames == 0


def test_no_pipewire_is_explained(monkeypatch):
    from soundboard import appaudio
    from soundboard.linux import appaudio as la
    monkeypatch.setattr(la.shutil, "which", lambda name: None)
    ok, why = appaudio.supported()
    assert not ok and "PipeWire" in why
    cap = appaudio.AppCapture(1, lambda x: None)
    assert not cap.start() and "PipeWire" in cap.error


def test_a_program_that_closed_is_said_so(monkeypatch):
    from soundboard import appaudio
    from soundboard.linux import appaudio as la
    monkeypatch.setattr(la.shutil, "which", lambda name: "/usr/bin/" + name)
    cap = appaudio.AppCapture(2 ** 22 + 12345, lambda x: None)   # no such process
    assert not cap.start() and cap.ended and "isn't running" in cap.error


def test_a_shared_helper_goes_to_the_program_that_started_it_on_linux(monkeypatch):
    # Linux's helpers by their Linux names, and nothing is folded into systemd
    from soundboard import appaudio
    from soundboard.linux import appaudio as la
    procs = {1: (0, "/usr/lib/systemd/systemd"), 900: (1, "/usr/lib/systemd/systemd"),
             40: (900, "/opt/steam/ubuntu12_32/steam"),
             41: (40, "/opt/steam/ubuntu12_64/steamwebhelper"),
             42: (41, "/opt/steam/ubuntu12_64/steamwebhelper"),
             60: (900, "/usr/lib/qt6/libexec/QtWebEngineProcess")}
    monkeypatch.setattr(la, "process_path", lambda pid: procs.get(pid, (0, ""))[1])
    monkeypatch.setattr(la, "_ppid", lambda pid: procs.get(pid, (0, ""))[0])
    table = la._process_table([42, 60])
    assert table[41] == (40, "steamwebhelper") and 900 not in table
    assert appaudio.root_pid(42) == 40      # Steam's store / overlay sound is Steam's
    assert appaudio.root_pid(60) == 60      # started by systemd: stays itself


def test_a_program_thats_gone_says_so_even_without_pipewire(monkeypatch):
    # CI's runner has no pw-dump: "not running" is still the answer that helps
    from soundboard import appaudio
    from soundboard.linux import appaudio as la
    monkeypatch.setattr(la.shutil, "which", lambda name: None)
    cap = appaudio.AppCapture(4_000_000_000 - 1, lambda x: None, name="nobody")
    assert cap.start() is False and "running" in cap.error and cap.ended
    monkeypatch.setattr(la, "is_running", lambda pid: True)
    cap = appaudio.AppCapture(4_000_000_000 - 1, lambda x: None, name="nobody")
    assert cap.start() is False and "PipeWire" in cap.error


def test_running_names_every_process_so_a_quiet_program_isnt_closed():
    """1.9's Apps tab keeps a quiet program's row when its process still runs
    (appaudio.running(); upstream's is {} off Windows: every quiet one looked closed)."""
    from soundboard import appaudio
    alive = appaudio.running()
    assert alive.get(os.getpid()) == os.path.basename(os.path.realpath(sys.executable)).lower()
    assert 9001000 not in alive


def test_stop_without_waiting_returns_at_once_and_feeds_nothing_more(monkeypatch):
    """start(wait=False) / stop(wait=False) (upstream 1.9, so a slow capture can't
    freeze the window): stop returns while the thread is still busy, and the old thread
    hands nothing to the sink after it."""
    import threading

    from soundboard.linux import appaudio as la
    opening, let_go = threading.Event(), threading.Event()

    class Reader:
        alive = True

        def take(self, n):
            return np.zeros((n, 2), np.float32)

        def stop(self):
            pass

    def slow_sync(self):   # "pw-record taking its time to start"
        opening.set()
        let_go.wait(5)
        self._readers = {"1": Reader()}
    monkeypatch.setattr(la.AppCapture, "_sync", slow_sync)
    monkeypatch.setattr(la, "is_running", lambda pid: True)
    monkeypatch.setattr(la, "supported", lambda: (True, ""))
    got = []
    cap = la.AppCapture(4242, got.append, name="slow")
    assert cap.start(wait=False) and opening.wait(2) and not cap.ready
    cap.stop(wait=False)
    assert cap._thread.is_alive()          # returned while the thread still waits
    let_go.set()
    cap.join(2)
    assert not cap._thread.is_alive() and got == [] and cap.frames == 0
