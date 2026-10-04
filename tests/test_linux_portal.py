"""soundboard/linux/portal.py: Wayland hotkeys through the GlobalShortcuts portal.
A private dbus-daemon carries the real D-Bus traffic; a stand-in portal answers
like the desktop would (it binds what it's asked, minus what the "user" refused)
and presses keys by sending Activated / Deactivated."""
import os
import shutil
import subprocess
import sys
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or not shutil.which("dbus-daemon"),
    reason="needs Linux and dbus-daemon")

from soundboard.linux import portal  # noqa: E402

IFACE = portal.IFACE


@pytest.fixture
def bus(monkeypatch, tmp_path):
    """A session bus of our own: DBUS_SESSION_BUS_ADDRESS points at it."""
    p = subprocess.Popen(["dbus-daemon", "--session", "--nofork", "--print-address=1",
                          "--nopidfile"], stdout=subprocess.PIPE, text=True)
    address = p.stdout.readline().strip()
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", address)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-test")
    monkeypatch.delenv("DISPLAY", raising=False)
    yield address
    p.terminate()
    p.wait(5)


class FakePortal:
    """org.freedesktop.portal.Desktop's GlobalShortcuts, as KDE / GNOME answer it."""

    def __init__(self, refuse=(), version=1):
        from jeepney import DBusAddress, message_bus
        from jeepney.io.blocking import open_dbus_connection
        self.refuse, self.version = set(refuse), version
        self.conn = open_dbus_connection(bus="SESSION")
        self.conn.send_and_get_reply(message_bus.RequestName(portal.BUS_NAME))
        self.bound: list = []          # what each BindShortcuts asked for
        self.sessions: list[str] = []
        self.closed: list[str] = []
        self.registered: list[str] = []
        self._emitter = DBusAddress(portal.PATH, interface=IFACE)
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def close(self):
        self._stop = True
        self._thread.join(5)
        self.conn.close()

    def press(self, session, sid, down=True):
        from jeepney import new_signal
        self.conn.send(new_signal(self._emitter, "Activated" if down else "Deactivated",
                                  "osta{sv}", (session, sid, 0, {})))

    def _respond(self, sender, token, results):
        from jeepney import DBusAddress, HeaderFields, new_signal
        path = f"{portal.PATH}/request/{sender.lstrip(':').replace('.', '_')}/{token}"
        msg = new_signal(DBusAddress(path, interface="org.freedesktop.portal.Request"),
                         "Response", "ua{sv}", (0, results))
        msg.header.fields[HeaderFields.destination] = sender   # for its caller only
        self.conn.send(msg)
        return path

    def _serve(self):
        from jeepney import HeaderFields as F
        from jeepney import MessageType, new_error, new_method_return
        while not self._stop:
            try:
                msg = self.conn.receive(timeout=0.1)
            except TimeoutError:
                continue
            except OSError:
                return
            if msg.header.message_type != MessageType.method_call:
                continue
            member, iface = msg.header.fields.get(F.member), msg.header.fields.get(F.interface)
            sender = msg.header.fields.get(F.sender)
            if member == "Get" and msg.body[1] == "version" and self.version:
                self.conn.send(new_method_return(msg, "v", (("u", self.version),)))
            elif member == "Register":
                self.registered.append(msg.body[0])
                self.conn.send(new_method_return(msg))
            elif member == "CreateSession":
                opts = msg.body[0]
                session = f"{portal.PATH}/session/x/{opts['session_handle_token'][1]}"
                self.sessions.append(session)
                path = f"{portal.PATH}/request/x/{opts['handle_token'][1]}"
                self.conn.send(new_method_return(msg, "o", (path,)))
                self._respond(sender, opts["handle_token"][1],
                              {"session_handle": ("s", session)})
            elif member == "BindShortcuts":
                session, shortcuts, _parent, opts = msg.body
                self.bound.append(shortcuts)
                kept = [(sid, {"description": o["description"],
                               "trigger_description": ("s", "whatever the user set")})
                        for sid, o in shortcuts if sid not in self.refuse]
                self.conn.send(new_method_return(msg, "o", (f"{portal.PATH}/request/x/b",)))
                self._respond(sender, opts["handle_token"][1],
                              {"shortcuts": ("a(sa{sv})", kept)})
            elif member == "Close" and iface == "org.freedesktop.portal.Session":
                self.closed.append(msg.header.fields.get(F.path))
                self.conn.send(new_method_return(msg))
            else:
                self.conn.send(new_error(msg, "org.freedesktop.DBus.Error.UnknownMethod"))


def _until(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        time.sleep(0.02)
    return cond()


def test_trigger_is_the_shortcut_specs_spelling():
    assert portal.trigger("ctrl+shift+f1") == "CTRL+SHIFT+F1"
    assert portal.trigger("alt+a") == "ALT+a"
    assert portal.trigger("windows+num 5") == "LOGO+KP_5"
    assert portal.trigger("ctrl+[") == "CTRL+bracketleft"
    assert portal.trigger("nonsense+key") == ""
    assert portal.shortcut_id("Ctrl+Shift+F1") == "combo-ctrl_shift_f1"


def test_hotkeys_are_bound_pressed_held_and_let_go(bus):
    fake = FakePortal(refuse={"combo-ctrl_f2"})
    fired, released, failed = [], [], []
    s = portal.Shortcuts(fired.append, released.append, failed.append)
    try:
        assert s.wait_ready(5) and s.alive
        assert portal.available()
        s.register({"ctrl+f1": "play:boom", "ctrl+f2": "stop"})
        assert _until(lambda: failed)
        assert failed == [["ctrl+f2"]]                       # the user didn't allow it
        (asked,) = fake.bound
        prefs = {sid: o.get("preferred_trigger", ("s", ""))[1] for sid, o in asked}
        assert prefs == {"combo-ctrl_f1": "CTRL+F1", "combo-ctrl_f2": "CTRL+F2"}
        assert fake.registered == [portal.APP_ID]
        session = fake.sessions[-1]
        fake.press(session, "combo-ctrl_f1")
        fake.press(session, "combo-ctrl_f1")                 # key repeat: one press
        assert _until(lambda: fired) and fired == ["play:boom"]
        fake.press(session, "combo-ctrl_f1", down=False)
        assert _until(lambda: released) and released == ["play:boom"]
        fake.press("/some/other/session", "combo-ctrl_f1")   # not ours
        fake.press(session, "combo-ctrl_f2")                 # not bound
        time.sleep(0.3)
        assert fired == ["play:boom"]
        # a new set: the old session closes, the new one is bound
        s.register({"alt+a": "play:x"})
        assert _until(lambda: len(failed) == 2) and failed[-1] == []
        assert fake.closed == [session] and len(fake.sessions) == 2
    finally:
        s.stop(5)
        fake.close()


def test_a_desktop_without_the_portal_reports_every_hotkey_failed(bus):
    fake = FakePortal(version=0)   # the service is there, GlobalShortcuts isn't
    try:
        assert not portal.available()
        s = portal.Shortcuts(lambda a: None, lambda a: None, lambda c: None)
        assert s.wait_ready(5) and not s.alive
        s.stop(2)
    finally:
        fake.close()


def test_linux_hotkeys_use_the_portal_on_wayland_without_x(bus, qapp):
    from soundboard.linux import keys
    fake = FakePortal()
    failed = []
    hk = keys.Hotkeys()
    try:
        hk.failed_changed.connect(failed.append)
        assert hk.alive and hk._portal is not None
        hk.register({"ctrl+f1": "play:boom"})
        from tests.conftest import process_events
        assert process_events(qapp, lambda: failed == [[]], timeout=5)
        fired = []
        hk.fired.connect(fired.append)
        fake.press(fake.sessions[-1], "combo-ctrl_f1")
        assert process_events(qapp, lambda: fired == ["play:boom"], timeout=5)
    finally:
        hk.stop(5)
        fake.close()
    assert os.environ.get("DISPLAY") is None
