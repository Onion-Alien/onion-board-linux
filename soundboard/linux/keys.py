"""Linux side of soundboard.winkeys: global hotkeys, key presses and the overlay's
window helpers. Star-imported at the bottom of winkeys.py, so everything here
replaces the Windows version of the same name; the portable parts of winkeys
(parse, combo_name, key_sequence, the VK table) are used as they are.

Hotkeys are X11 key grabs (soundboard.linux.x11), which also work in games running
under XWayland on a Wayland desktop while the game has focus. Without an X server
(a Wayland session with no XWayland) they go through the desktop's GlobalShortcuts
portal (soundboard.linux.portal: KDE Plasma, GNOME 48+); with neither, keyboard
hotkeys report as failed. MIDI pads work everywhere.

Like RegisterHotKey, a grab only tells us about our own combos and never sits in
the path of other keys. X starts a keyboard grab when a grabbed key goes down; it's
ended at once, and the key's release is watched by polling the key state
(HELD_POLL_MS), the same as the Windows version does.
"""
from __future__ import annotations

import logging
import os
import select
import threading

from PySide6.QtCore import QObject, Signal

from soundboard import midi
from soundboard.linux import portal, x11

log = logging.getLogger(__name__)


def _w():
    """soundboard.winkeys, looked up when needed: it star-imports this module at its
    end, so importing it from up here would hand it a half-loaded copy."""
    from soundboard import winkeys
    return winkeys

__all__ = ["Hotkeys", "close_shared", "event_vk", "key_char", "press", "release", "is_down",
           "exclusive_fullscreen", "foreground_monitor_info", "foreground_monitor",
           "make_overlay", "raise_topmost"]

_RELEVANT = (x11.ShiftMask | x11.ControlMask | x11.Mod1Mask | x11.Mod4Mask)


class Hotkeys(QObject):
    """X11 key grabs on a private thread; same interface as winkeys.Hotkeys:
    `fired(action)` / `released(action)` on the Qt thread, `failed_changed(list)` after
    every `register` with the combos that couldn't be had."""
    fired = Signal(str)
    released = Signal(str)
    failed_changed = Signal(list)

    def __init__(self, midi_in: midi.MidiIn | None = None):
        super().__init__()
        self.failed: list[str] = []
        self.midi = midi_in or midi.MidiIn()
        self._midi_map: dict[str, str] = {}
        self.midi.pressed.connect(self._midi_pressed)
        self.midi.released.connect(self._midi_released)
        self._pending: dict[str, str] | None = None
        self._lock = threading.Lock()
        self._wake_r, self._wake_w = os.pipe()
        self._quit = False
        self._alive = False
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._portal = None
        wayland = portal.wayland()
        # a Wayland desktop: its GlobalShortcuts portal, even with XWayland there (X11
        # grabs only see keys while an X11 window is in front); X11 grabs on X11, or
        # on a Wayland desktop with no portal (Sway, older GNOME: games under XWayland)
        if wayland and (not x11.available() or portal.available()):
            self._portal = portal.Shortcuts(self.fired.emit, self.released.emit,
                                            self._portal_failed)
            if not self._portal.wait_ready(2):
                log.error("portal hotkey thread didn't start")
        elif x11.available():
            if wayland:
                log.warning("no GlobalShortcuts portal: hotkeys only reach the app while "
                            "an X11 window is in front")
            self._thread = threading.Thread(target=self._loop, daemon=True, name="hotkeys")
            self._thread.start()
            if not self._ready.wait(2):
                log.error("hotkey thread didn't start; global hotkeys won't work this session")
        else:
            log.warning("no X display: keyboard hotkeys are off this session (MIDI pads work)")
        self._wayland = wayland

    @property
    def alive(self) -> bool:
        return self._portal.alive if self._portal is not None else self._alive

    @property
    def why(self) -> str:
        """Why keyboard hotkeys don't work everywhere, for linux/ui.py's words: "" (they
        do, or a key is another program's), "x11-only" (a Wayland desktop with no
        portal: only while an X11 window is in front), "no-portal" (nothing at all),
        "declined" (the user said no to the desktop's dialog), "failed"."""
        if self._portal is not None:
            return self._portal.why if self._portal.alive else (self._portal.why or "no-portal")
        if self._wayland:
            return "x11-only" if self._alive else "no-portal"
        return ""

    def _portal_failed(self, combos: list):
        self.failed = list(combos)
        self.failed_changed.emit(list(combos))

    def register(self, mapping: dict[str, str]):
        """mapping: combo -> action. Replaces all current hotkeys."""
        self._midi_map = {c: a for c, a in mapping.items() if midi.is_midi(c)}
        self.midi.want({p[2] for p in map(midi.parse, self._midi_map) if p})
        keys = {c: a for c, a in mapping.items() if not midi.is_midi(c)}
        if self._portal is not None and self._portal.alive:
            self._portal.register(keys)
            return
        if not self._alive:
            self.failed = [c for c in keys if c]
            self.failed_changed.emit(list(self.failed))
            return
        with self._lock:
            self._pending = keys
        self._wake()

    def pause(self):
        self.register({})

    def stop(self, wait: float = 0.0):
        """Let every hotkey go; `wait` seconds for the thread to have done so."""
        self.midi.close_all()
        self._quit = True
        self._wake()
        if self._portal is not None:
            self._portal.stop(wait)
        if wait and self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(wait)

    def _wake(self):
        try:
            os.write(self._wake_w, b"x")
        except OSError:
            pass

    def _midi_pressed(self, combo: str):
        act = self._midi_map.get(combo)
        if act:
            self.fired.emit(act)

    def _midi_released(self, combo: str):
        act = self._midi_map.get(combo)
        if act:
            self.released.emit(act)

    # -- the hotkey thread
    def _loop(self):
        grabs: dict[tuple[int, int], tuple[str, int]] = {}   # (keycode, mods) -> (action, vk)
        held: dict[int, tuple[str, int]] = {}                # keycode -> (action, vk)
        try:
            d = x11.Display()
        except OSError:
            log.warning("can't open the X display: keyboard hotkeys are off")
            self._ready.set()
            return
        try:
            d.detectable_autorepeat()
            self._alive = True
            self._ready.set()
            fd = d.fileno()
            while not self._quit and d.alive:
                timeout = _w().HELD_POLL_MS / 1000 if held else None
                if not d.pending():
                    r, _w2, _x = select.select([fd, self._wake_r], [], [], timeout)
                    if self._wake_r in r:
                        os.read(self._wake_r, 64)
                        self._apply(d, grabs)
                while d.alive and d.pending():
                    ev = d.next_event()
                    if ev.type == x11.KeyPress:
                        k = ev.xkey
                        hit = grabs.get((k.keycode, k.state & _RELEVANT))
                        d.ungrab_keyboard()
                        if hit and k.keycode not in held:
                            held[k.keycode] = hit
                            self.fired.emit(hit[0])
                if held and d.alive:
                    keymap = d.keymap()
                    for kc, (act, _vk) in list(held.items()):
                        if not keymap[kc >> 3] & (1 << (kc & 7)):
                            del held[kc]
                            self.released.emit(act)
        except Exception:  # noqa: BLE001
            from soundboard import applog
            applog.report(where="hotkey thread")
        finally:
            self._alive = False
            self._ready.set()
            if d.alive:
                for kc, mods in list(grabs):
                    try:
                        d.ungrab(kc, mods)
                    except Exception:  # noqa: BLE001
                        pass
            d.close()

    def _apply(self, d: x11.Display, grabs: dict):
        with self._lock:
            mapping, self._pending = self._pending, None
        if mapping is None:
            return
        for kc, mods in list(grabs):
            d.ungrab(kc, mods)
        grabs.clear()
        failed = []
        for combo, act in mapping.items():
            if not combo:
                continue
            parsed = _w().parse(combo)
            kc = d.keycode(parsed[1]) if parsed else 0
            if not parsed or not kc:
                failed.append(combo)
                continue
            mods = x11.x_mods(parsed[0])
            if (kc, mods) in grabs or d.grab(kc, mods):
                grabs[(kc, mods)] = (act, parsed[1])
            else:
                failed.append(combo)
        self.failed = failed
        self.failed_changed.emit(list(failed))


# ---------------------------------------------------------------- key events
_display: x11.Display | None = None
_display_lock = threading.Lock()


def _shared() -> x11.Display | None:
    """A connection for the UI thread's queries and key presses."""
    global _display
    with _display_lock:
        if _display is not None and not _display.alive:
            _display = None   # its X server went away: try a new one
        if _display is None and x11.available():
            try:
                _display = x11.Display()
            except OSError:
                _display = None
        return _display


def close_shared():
    """Close the UI thread's X connection (tests, before their X server goes)."""
    global _display
    with _display_lock:
        if _display is not None:
            _display.close()
            _display = None


def event_vk(e) -> int:
    """The Windows virtual-key code of a Qt key event. Qt reports the X keysym on
    Linux; the unshifted one is looked up from the key code, so Shift+1 is "1"."""
    d = _shared()
    code = e.nativeScanCode()
    if d is not None and code:
        vk = x11.keysym_to_vk(d.keysym(code, 0))
        if vk:
            return vk
    vk = x11.keysym_to_vk(e.nativeVirtualKey())
    if vk:
        return vk
    return x11.EVDEV_TO_VK.get(code - 8, 0) if code else 0


def key_char(vk: int) -> str:
    """What the key types on the current keyboard layout ("" if nothing)."""
    d = _shared()
    if d is not None:
        kc = d.keycode(vk)
        ks = d.keysym(kc, 0) if kc else 0
        if 0x20 < ks < 0x7F or 0xA0 <= ks <= 0xFF:
            return chr(ks)
        if 0x01000100 <= ks <= 0x0110FFFF:   # Unicode keysyms
            return chr(ks - 0x01000000)
    name = _w().NAME.get(vk, "")
    return name if len(name) == 1 else ""


def _send_all(events: list[tuple[int, bool]]) -> bool:
    d = _shared()
    if d is None:
        return False
    ok = True
    for vk, up in events:
        ok = d.fake_key(d.keycode(vk), not up) and ok
    if not ok:
        log.warning("XTest couldn't send %d key events", len(events))
    return ok


def press(combo: str) -> bool:
    """Hold a key (with its modifiers) down, e.g. a game's push-to-talk key."""
    events = _w().key_sequence(combo, up=False)
    return events is not None and _send_all(events)


def release(combo: str) -> bool:
    events = _w().key_sequence(combo, up=True)
    return events is not None and _send_all(events)


def is_down(vk: int) -> bool:
    d = _shared()
    if d is None:
        return False
    kc = d.keycode(vk)
    if not kc:
        return False
    return bool(d.keymap()[kc >> 3] & (1 << (kc & 7)))


def exclusive_fullscreen() -> bool:
    return False   # no exclusive fullscreen on X11 / Wayland: an overlay can always draw


def foreground_monitor_info() -> tuple[str, tuple[int, int, int, int] | None]:
    """The monitor the window in front (the game) is on: ('', its rectangle in native
    pixels), which overlay.pick_screen matches as on Windows; ('', None) when that
    can't be told (no X11, a Wayland window in front)."""
    from PySide6.QtGui import QGuiApplication
    from soundboard.linux import voicesdk
    r = voicesdk.active_window_rect()
    if not r:
        return "", None
    cx, cy = r[0] + r[2] // 2, r[1] + r[3] // 2
    for sc in QGuiApplication.screens():
        g, k = sc.geometry(), sc.devicePixelRatio()
        x, y, w, h = g.left(), g.top(), round(g.width() * k), round(g.height() * k)
        if x <= cx < x + w and y <= cy < y + h:
            return "", (x, y, w, h)
    return "", None


def foreground_monitor() -> str:
    return ""


def make_overlay(hwnd: int):
    pass   # Qt's window flags (Tool, StaysOnTop, DoesNotAcceptFocus) do it on X11


def raise_topmost(hwnd: int):
    pass
