"""Global hotkeys on Wayland: the desktop's GlobalShortcuts portal
(org.freedesktop.portal.GlobalShortcuts, over D-Bus with jeepney).

A Wayland app can't grab keys itself. It hands the desktop a list of shortcuts (an
id, a description, the keys it would like); the desktop asks the user once, binds
them, and then says when one goes down (Activated) and up (Deactivated), so
hold-to-play works as with X11. The desktop may bind other keys than the ones asked
for, or none: what it bound comes back, and anything it didn't is reported as
failed, like a combo another program holds on X11. KDE Plasma and GNOME (48 and
newer) have the portal; elsewhere keyboard hotkeys stay off (MIDI pads still work).

A Wayland desktop's portal is used even when XWayland is there too (DISPLAY set, as
on every normal GNOME / Plasma login): X11 grabs there only see keys while an X11
window is in front (GNOME 50: nothing reached them with the app's own window or a
terminal in front).

Shortcuts belong to a session; a changed set of hotkeys closes the session and
binds the new set in a fresh one.
"""
from __future__ import annotations

import collections
import logging
import secrets
import threading
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

BUS_NAME = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
IFACE = "org.freedesktop.portal.GlobalShortcuts"
# The id the portal knows the app by. It must be a valid GApplication id (reverse
# DNS, with dots): GNOME's shortcuts provider throws the bind away otherwise
# ("invalid app_id >onionboard<", GNOME 50) where Plasma took the bare name.
APP_ID = "io.github.Onion_Alien.OnionBoard"
OLD_APP_IDS = ("onionboard",)   # hidden .desktop files earlier versions wrote
TIMEOUT_S = 5.0         # a portal call's reply (not the user's answer to the dialog)
ANSWER_S = 300.0        # the user answering the desktop's "allow these shortcuts?" dialog
POLL_S = 0.25           # how often the thread looks for a changed set of hotkeys
# action -> the words the desktop shows for it ("Stop everything", "Play Airhorn");
# linux/ui.py sets it from the main window, which knows the sounds' names
describe: Callable[[str], str] = str
REGISTER_TRIES = 5      # the portal may not have noticed a just-written .desktop file
REGISTER_WAIT_S = 0.4
# Set = binding may start. linux/ui.py clears it while the app starts and sets it once
# its windows are up: GNOME's "allow these shortcuts?" dialog has no parent, so one
# opened before the window (and the first start's setup guide) ended up under them,
# unseen, and the hotkeys never came (Ubuntu 26.04, GNOME 50).
may_bind = threading.Event()
may_bind.set()

# winkeys MOD_* -> the XDG shortcuts spec's modifier names
_MODS = ((0x2, "CTRL"), (0x1, "ALT"), (0x4, "SHIFT"), (0x8, "LOGO"))
# X keysym -> its name, for the keys the VK table has (xkbcommon's names)
_NAMED = {
    0x20: "space", 0xFF0D: "Return", 0xFF09: "Tab", 0xFF1B: "Escape", 0xFF08: "BackSpace",
    0xFF63: "Insert", 0xFFFF: "Delete", 0xFF50: "Home", 0xFF57: "End", 0xFF55: "Prior",
    0xFF56: "Next", 0xFF52: "Up", 0xFF54: "Down", 0xFF51: "Left", 0xFF53: "Right",
    0xFF13: "Pause", 0xFF61: "Print", 0xFF14: "Scroll_Lock", 0xFFE5: "Caps_Lock",
    0xFF7F: "Num_Lock", 0xFF67: "Menu", 0xFFAA: "KP_Multiply", 0xFFAB: "KP_Add",
    0xFFAD: "KP_Subtract", 0xFFAE: "KP_Decimal", 0xFFAF: "KP_Divide",
    0x3B: "semicolon", 0x3D: "equal", 0x2C: "comma", 0x2D: "minus", 0x2E: "period",
    0x2F: "slash", 0x60: "grave", 0x5B: "bracketleft", 0x5C: "backslash",
    0x5D: "bracketright", 0x27: "apostrophe",
    0x1008FF14: "XF86AudioPlay", 0x1008FF17: "XF86AudioNext", 0x1008FF16: "XF86AudioPrev",
    0x1008FF13: "XF86AudioRaiseVolume", 0x1008FF11: "XF86AudioLowerVolume",
    0x1008FF12: "XF86AudioMute",
}
_NAMED.update({0xFFBE + i: f"F{i + 1}" for i in range(24)})
_NAMED.update({0xFFB0 + d: f"KP_{d}" for d in range(10)})


def desktop_entry() -> Path:
    from soundboard.linux import data_home
    return Path(data_home()) / "applications" / f"{APP_ID}.desktop"


def write_desktop_entry() -> bool:
    """The .desktop file the portal looks the app id up in (xdg-desktop-portal's
    Registry refuses an id without one: "App info not found"). An AppImage installs
    none, so the app writes its own, hidden (NoDisplay: no new menu entry), and keeps
    its Exec pointing at wherever the app runs from. True if it's there."""
    from soundboard.linux import autostart
    p = desktop_entry()
    for old in OLD_APP_IDS:
        try:
            (p.parent / f"{old}.desktop").unlink(missing_ok=True)
        except OSError:
            pass
    text =("[Desktop Entry]\nType=Application\nName=Onion Board\n"
            f"Exec={autostart.command(False)}\nIcon={APP_ID}\nTerminal=false\n"
            "NoDisplay=true\n")
    try:
        if p.is_file() and p.read_text(encoding="utf-8") == text:
            return True
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(p)
        return True
    except OSError:
        log.warning("couldn't write %s: the portal may not take the app id", p, exc_info=True)
        return False


def trigger(combo: str) -> str:
    """A combo ("ctrl+shift+f1") as the portal's preferred trigger ("CTRL+SHIFT+F1"),
    or "" when it has no key the table knows."""
    from soundboard import winkeys
    from soundboard.linux import x11
    parsed = winkeys.parse(combo)
    if not parsed:
        return ""
    ks = x11.vk_to_keysym(parsed[1])
    if ks is None:
        return ""
    name = chr(ks) if 0x30 <= ks <= 0x39 or 0x61 <= ks <= 0x7A else _NAMED.get(ks, "")
    if not name:
        return ""
    return "+".join([n for bit, n in _MODS if parsed[0] & bit] + [name])


def shortcut_id(combo: str) -> str:
    """A stable id for a combo: the desktop remembers what the user bound per id."""
    return "combo-" + "".join(c if c.isalnum() else "_" for c in combo.lower())


def wayland() -> bool:
    import os
    env = os.environ
    return bool(env.get("WAYLAND_DISPLAY")) or env.get("XDG_SESSION_TYPE") == "wayland"


def available() -> bool:
    """A Wayland session whose portal has GlobalShortcuts."""
    if not wayland():
        return False
    try:
        conn = _connect()
    except Exception:  # noqa: BLE001 - no session bus, no jeepney
        return False
    try:
        return _version(conn) > 0
    finally:
        conn.close()


def _connect():
    from jeepney.io.blocking import open_dbus_connection
    return open_dbus_connection(bus="SESSION")


def _version(conn) -> int:
    from jeepney import DBusAddress, Properties
    try:
        reply = conn.send_and_get_reply(
            Properties(DBusAddress(PATH, BUS_NAME, IFACE)).get("version"), timeout=TIMEOUT_S)
    except Exception:  # noqa: BLE001
        return 0
    body = reply.body[0] if reply.body else None
    return int(body[1]) if isinstance(body, tuple) and len(body) == 2 else 0


class PortalError(Exception):
    pass


class Shortcuts:
    """The portal's shortcuts on a private thread. `on_fired(action)` /
    `on_released(action)` when a bound one goes down / up, `on_failed(combos)` after
    each set is bound with the ones the desktop didn't bind (all of them when there's
    no portal or the user said no). Callbacks run on this object's thread."""

    def __init__(self, on_fired: Callable[[str], None], on_released: Callable[[str], None],
                 on_failed: Callable[[list[str]], None]):
        self.on_fired, self.on_released, self.on_failed = on_fired, on_released, on_failed
        self._lock = threading.Lock()
        self._pending: dict[str, str] | None = None
        self._quit = threading.Event()
        self._ready = threading.Event()
        self.alive = False
        # why the last set wasn't bound, for the window's words: "" (it was, or only some
        # keys weren't), "no-portal", "declined" (the user said no) or "failed"
        self.why = ""
        self._thread = threading.Thread(target=self._run, daemon=True, name="portal-hotkeys")
        self._thread.start()

    def wait_ready(self, timeout: float) -> bool:
        return self._ready.wait(timeout)

    def register(self, mapping: dict[str, str]):
        """combo -> action; replaces the current set."""
        with self._lock:
            self._pending = {c: a for c, a in mapping.items() if c}

    def stop(self, wait: float = 0.0):
        self._quit.set()
        if wait and self._thread is not threading.current_thread():
            self._thread.join(wait)

    # -- the thread
    def _run(self):
        try:
            conn = _connect()
        except Exception:  # noqa: BLE001
            log.warning("no D-Bus session bus: keyboard hotkeys are off this session")
            self._ready.set()
            return
        try:
            if _version(conn) <= 0:
                self.why = "no-portal"
                log.warning("the desktop has no GlobalShortcuts portal: keyboard hotkeys "
                            "are off this session (MIDI pads work)")
                return
            self._register_app(conn)
            self.alive = True
            self._ready.set()
            self._loop(conn)
        except Exception:  # noqa: BLE001
            from soundboard import applog
            applog.report(where="portal hotkey thread")
        finally:
            self.alive = False
            self._ready.set()
            conn.close()

    def _register_app(self, conn):
        """Tell the portal which app this is (xdg-desktop-portal 1.19+, for apps that
        aren't Flatpaks or Snaps); older portals don't have it, which is fine. The
        portal only takes an id it finds a .desktop file for, so that's written first;
        it can take a moment to notice a new one."""
        from jeepney import DBusAddress, new_method_call
        from jeepney import HeaderFields, MessageType
        write_desktop_entry()
        for attempt in range(REGISTER_TRIES):
            msg = new_method_call(
                DBusAddress(PATH, BUS_NAME, "org.freedesktop.host.portal.Registry"),
                "Register", "sa{sv}", (APP_ID, {}))
            try:
                reply = conn.send_and_get_reply(msg, timeout=TIMEOUT_S)
            except Exception:  # noqa: BLE001
                log.debug("portal registry: not there", exc_info=True)
                return
            if reply.header.message_type != MessageType.error:
                return
            name = str(reply.header.fields.get(HeaderFields.error_name, ""))
            if name.endswith(("UnknownMethod", "UnknownInterface")):
                return   # an older portal: it needs no app id
            if attempt == REGISTER_TRIES - 1:
                log.warning("the portal didn't take the app id %r: %s", APP_ID,
                            reply.body[0] if reply.body else name)
            else:
                self._quit.wait(REGISTER_WAIT_S)

    def _loop(self, conn):
        from jeepney import HeaderFields, MatchRule, message_bus
        session = ""
        actions: dict[str, str] = {}     # shortcut id -> action
        down: set[str] = set()
        signals = collections.deque()
        handles = []   # kept: a filter lasts as long as its handle
        for member in ("Activated", "Deactivated"):
            rule = MatchRule(type="signal", interface=IFACE, member=member, path=PATH)
            conn.send_and_get_reply(message_bus.AddMatch(rule), timeout=TIMEOUT_S)
            handles.append(conn.filter(rule, queue=signals))
        while not self._quit.is_set():
            with self._lock:
                if may_bind.is_set():
                    mapping, self._pending = self._pending, None
                else:
                    mapping = None
            if mapping is not None:
                for sid in list(down):   # a key held across a change: let it go
                    if sid in actions:
                        self.on_released(actions[sid])
                down.clear()
                if session:
                    self._close(conn, session)
                session, actions = "", {}
                if mapping:
                    session, actions = self._bind(conn, mapping)
            try:
                signals.appendleft(conn.recv_until_filtered(signals, timeout=POLL_S))
            except TimeoutError:
                pass
            while signals:
                msg = signals.popleft()
                sess, sid = msg.body[0], msg.body[1]
                if sess != session or sid not in actions:
                    continue
                if msg.header.fields.get(HeaderFields.member) == "Activated":
                    if sid not in down:
                        down.add(sid)
                        self.on_fired(actions[sid])
                elif sid in down:
                    down.discard(sid)
                    self.on_released(actions[sid])
        if session:
            self._close(conn, session)

    def _request(self, conn, method: str, signature: str, args: tuple, token: str,
                 wait: float) -> dict:
        """Call a portal method that answers through a Request object's Response
        signal; its results, or PortalError."""
        from jeepney import DBusAddress, MatchRule, MessageType, message_bus, new_method_call
        sender = conn.unique_name.lstrip(":").replace(".", "_")
        path = f"{PATH}/request/{sender}/{token}"
        rule = MatchRule(type="signal", interface="org.freedesktop.portal.Request",
                         member="Response", path=path)
        conn.send_and_get_reply(message_bus.AddMatch(rule), timeout=TIMEOUT_S)
        try:
            with conn.filter(rule, bufsize=4) as answers:
                reply = conn.send_and_get_reply(
                    new_method_call(DBusAddress(PATH, BUS_NAME, IFACE), method, signature, args),
                    timeout=TIMEOUT_S)
                if reply.header.message_type == MessageType.error:
                    raise PortalError(f"{method}: {reply.body[0] if reply.body else 'error'}")
                answer, left = None, wait
                while answer is None and left > 0 and not self._quit.is_set():
                    try:
                        answer = conn.recv_until_filtered(answers, timeout=min(POLL_S, left))
                    except TimeoutError:
                        left -= POLL_S
                if answer is None:
                    raise PortalError(f"{method}: no answer")
                code, results = answer.body
        finally:
            try:
                conn.send_and_get_reply(message_bus.RemoveMatch(rule), timeout=TIMEOUT_S)
            except Exception:  # noqa: BLE001
                pass
        if code != 0:   # 1: the user said no, 2: something else
            raise PortalError(f"{method}: {'declined' if code == 1 else 'failed'}")
        return {k: v[1] for k, v in results.items()}

    def _bind(self, conn, mapping: dict[str, str]) -> tuple[str, dict[str, str]]:
        """A session with `mapping` bound: (session handle, shortcut id -> action)."""
        ids = {shortcut_id(c): (c, a) for c, a in mapping.items()}
        try:
            token = "onionboard_" + secrets.token_hex(6)
            res = self._request(conn, "CreateSession", "a{sv}",
                                ({"handle_token": ("s", token),
                                  "session_handle_token": ("s", "onionboard_s" + token[11:])},),
                                token, TIMEOUT_S)
            session = str(res.get("session_handle", ""))
            if not session:
                raise PortalError("CreateSession: no session")
            shortcuts = []
            for sid, (combo, action) in ids.items():
                try:
                    what = describe(action) or action
                except Exception:  # noqa: BLE001 - only words
                    what = action
                opts = {"description": ("s", f"Onion Board: {what}")}
                pref = trigger(combo)
                if pref:
                    opts["preferred_trigger"] = ("s", pref)
                shortcuts.append((sid, opts))
            token = "onionboard_" + secrets.token_hex(6)
            res = self._request(conn, "BindShortcuts", "oa(sa{sv})sa{sv}",
                                (session, shortcuts, "", {"handle_token": ("s", token)}),
                                token, ANSWER_S)
        except PortalError as e:
            log.warning("portal hotkeys: %s", e)
            self.why = "declined" if str(e).endswith("declined") else "failed"
            self.on_failed(sorted(mapping))
            return "", {}
        bound = {sid for sid, _opts in res.get("shortcuts", [])}
        failed = sorted(c for sid, (c, _a) in ids.items() if sid not in bound)
        log.info("portal bound %d of %d hotkeys", len(bound & set(ids)), len(ids))
        self.why = ""
        self.on_failed(failed)
        return session, {sid: a for sid, (_c, a) in ids.items() if sid in bound}

    def _close(self, conn, session: str):
        from jeepney import DBusAddress, new_method_call
        try:
            conn.send_and_get_reply(new_method_call(
                DBusAddress(session, BUS_NAME, "org.freedesktop.portal.Session"), "Close"),
                timeout=TIMEOUT_S)
        except Exception:  # noqa: BLE001
            log.debug("closing the portal session failed", exc_info=True)
