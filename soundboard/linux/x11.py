"""Just enough Xlib (over ctypes, no extra packages) for global hotkeys, key presses
and key state on X11, which also covers games under XWayland (Proton, most of
Steam) on a Wayland desktop.

  XGrabKey     a hotkey: the X server tells us about *our* combos only (like
               RegisterHotKey), key press and key release both, so hold-to-play
               needs no polling
  XTest        a fake key press for auto push-to-talk (SendInput's job)
  XQueryKeymap is a key down right now (GetAsyncKeyState's job)

Keys are stored as Windows virtual-key codes (config files move between the two),
so this module also maps VK codes to X keysyms and back.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os
import threading
from ctypes import (POINTER, Structure, Union, byref, c_char, c_char_p, c_int, c_long, c_uint,
                    c_ulong, c_void_p)

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ VK <-> keysym
_VK_TO_KEYSYM: dict[int, int] = {}
_VK_TO_KEYSYM.update({c: c + 0x20 for c in range(0x41, 0x5B)})          # A-Z -> a-z
_VK_TO_KEYSYM.update({c: c for c in range(0x30, 0x3A)})                  # 0-9
_VK_TO_KEYSYM.update({0x6F + i: 0xFFBD + i for i in range(1, 25)})       # F1-F24
_VK_TO_KEYSYM.update({0x60 + d: 0xFFB0 + d for d in range(10)})          # num 0-9
_VK_TO_KEYSYM.update({
    0x6A: 0xFFAA, 0x6B: 0xFFAB, 0x6D: 0xFFAD, 0x6E: 0xFFAE, 0x6F: 0xFFAF,  # num * + - . /
    0x20: 0x0020, 0x0D: 0xFF0D, 0x09: 0xFF09, 0x1B: 0xFF1B, 0x08: 0xFF08,
    0x2D: 0xFF63, 0x2E: 0xFFFF, 0x24: 0xFF50, 0x23: 0xFF57,
    0x21: 0xFF55, 0x22: 0xFF56, 0x26: 0xFF52, 0x28: 0xFF54, 0x25: 0xFF51, 0x27: 0xFF53,
    0x13: 0xFF13, 0x2C: 0xFF61, 0x91: 0xFF14, 0x14: 0xFFE5, 0x90: 0xFF7F, 0x5D: 0xFF67,
    0xBA: 0x3B, 0xBB: 0x3D, 0xBC: 0x2C, 0xBD: 0x2D, 0xBE: 0x2E, 0xBF: 0x2F, 0xC0: 0x60,
    0xDB: 0x5B, 0xDC: 0x5C, 0xDD: 0x5D, 0xDE: 0x27,
    0xB3: 0x1008FF14, 0xB0: 0x1008FF17, 0xB1: 0x1008FF16,                # media
    0xAF: 0x1008FF13, 0xAE: 0x1008FF11, 0xAD: 0x1008FF12,                # volume
    # modifiers (for key presses and key state)
    0x10: 0xFFE1, 0xA0: 0xFFE1, 0xA1: 0xFFE2, 0x11: 0xFFE3, 0xA2: 0xFFE3, 0xA3: 0xFFE4,
    0x12: 0xFFE9, 0xA4: 0xFFE9, 0xA5: 0xFFEA, 0x5B: 0xFFEB, 0x5C: 0xFFEC,
})
_KEYSYM_TO_VK: dict[int, int] = {}
for _vk, _ks in _VK_TO_KEYSYM.items():
    _KEYSYM_TO_VK.setdefault(_ks, _vk)
_KEYSYM_TO_VK.update({ks: ks for ks in range(0x41, 0x5B)})               # A-Z (shifted)
_KEYSYM_TO_VK.update({0xFF8D: 0x0D, 0xFE20: 0x09,                        # KP_Enter, ISO_Left_Tab
                      0xFF95: 0x24, 0xFF9C: 0x23, 0xFF9A: 0x21, 0xFF9B: 0x22,  # KP_Home…
                      0xFF96: 0x25, 0xFF97: 0x26, 0xFF98: 0x27, 0xFF99: 0x28,
                      0xFF9E: 0x2D, 0xFF9F: 0x2E, 0xFFE7: 0x5B, 0xFFE8: 0x5C,
                      0xFE03: 0xA5})   # ISO_Level3_Shift (AltGr)


def vk_to_keysym(vk: int) -> int | None:
    return _VK_TO_KEYSYM.get(vk)


def keysym_to_vk(ks: int) -> int:
    """0 if the keysym has no Windows key code."""
    return _KEYSYM_TO_VK.get(ks, 0)


# Linux evdev key codes (X keycode = evdev + 8) -> VK, a US layout: what a key event's
# scan code means when there's no X server to ask (Wayland without XWayland)
EVDEV_TO_VK: dict[int, int] = {
    1: 0x1B, 14: 0x08, 15: 0x09, 28: 0x0D, 57: 0x20, 58: 0x14, 69: 0x90, 70: 0x91,
    12: 0xBD, 13: 0xBB, 26: 0xDB, 27: 0xDD, 39: 0xBA, 40: 0xDE, 41: 0xC0, 43: 0xDC,
    51: 0xBC, 52: 0xBE, 53: 0xBF, 55: 0x6A, 74: 0x6D, 78: 0x6B, 83: 0x6E, 96: 0x0D,
    98: 0x6F, 99: 0x2C, 102: 0x24, 103: 0x26, 104: 0x21, 105: 0x25, 106: 0x27, 107: 0x23,
    108: 0x28, 109: 0x22, 110: 0x2D, 111: 0x2E, 119: 0x13, 127: 0x5D,
    113: 0xAD, 114: 0xAE, 115: 0xAF, 163: 0xB0, 164: 0xB3, 165: 0xB1,
    29: 0xA2, 97: 0xA3, 42: 0xA0, 54: 0xA1, 56: 0xA4, 100: 0xA5, 125: 0x5B, 126: 0x5C,
}
EVDEV_TO_VK.update({2 + i: 0x31 + i for i in range(9)})
EVDEV_TO_VK[11] = 0x30
for _row, _keys in ((16, "QWERTYUIOP"), (30, "ASDFGHJKL"), (44, "ZXCVBNM")):
    EVDEV_TO_VK.update({_row + i: ord(k) for i, k in enumerate(_keys)})
EVDEV_TO_VK.update({59 + i: 0x70 + i for i in range(10)})                # F1-F10
EVDEV_TO_VK.update({87: 0x7A, 88: 0x7B})                                  # F11, F12
EVDEV_TO_VK.update({183 + i: 0x7C + i for i in range(12)})               # F13-F24
EVDEV_TO_VK.update({71: 0x67, 72: 0x68, 73: 0x69, 75: 0x64, 76: 0x65, 77: 0x66,
                    79: 0x61, 80: 0x62, 81: 0x63, 82: 0x60})              # numpad digits

# X modifier masks
ShiftMask, LockMask, ControlMask, Mod1Mask, Mod2Mask, Mod4Mask = 1, 2, 4, 8, 16, 64
# winkeys MOD_* -> X mask
_MODS = ((0x2, ControlMask), (0x1, Mod1Mask), (0x4, ShiftMask), (0x8, Mod4Mask))
# grabs are exact about modifiers: Caps Lock / Num Lock on must not break a hotkey
_LOCK_VARIANTS = (0, LockMask, Mod2Mask, LockMask | Mod2Mask)


def x_mods(win_mods: int) -> int:
    m = 0
    for flag, mask in _MODS:
        if win_mods & flag:
            m |= mask
    return m


# ------------------------------------------------------------------ libX11
KeyPress, KeyRelease = 2, 3
GrabModeAsync = 1
BadAccess = 10


class XKeyEvent(Structure):
    _fields_ = [("type", c_int), ("serial", c_ulong), ("send_event", c_int),
                ("display", c_void_p), ("window", c_ulong), ("root", c_ulong),
                ("subwindow", c_ulong), ("time", c_ulong), ("x", c_int), ("y", c_int),
                ("x_root", c_int), ("y_root", c_int), ("state", c_uint),
                ("keycode", c_uint), ("same_screen", c_int)]


class XEvent(Union):
    _fields_ = [("type", c_int), ("xkey", XKeyEvent), ("pad", c_long * 24)]


class XErrorEvent(Structure):
    _fields_ = [("type", c_int), ("display", c_void_p), ("resourceid", c_ulong),
                ("serial", c_ulong), ("error_code", ctypes.c_ubyte),
                ("request_code", ctypes.c_ubyte), ("minor_code", ctypes.c_ubyte)]


_ErrorHandler = ctypes.CFUNCTYPE(c_int, c_void_p, POINTER(XErrorEvent))

_lib = None
_xtst = None
_lib_lock = threading.Lock()
_errors: list[int] = []     # error codes seen by the handler since the last check


def _on_error(_dpy, ev):
    try:
        _errors.append(ev.contents.error_code)
    except Exception:  # noqa: BLE001 - never raise into Xlib
        pass
    return 0


_handler = _ErrorHandler(_on_error)   # kept alive for the process
_IOExitHandler = ctypes.CFUNCTYPE(None, c_void_p, c_void_p)
lost: set[int] = set()     # displays whose X server went away


def _on_io_exit(dpy, _user):
    # Xlib's default here is exit(): a vanished X server (a logout, a test's Xvfb)
    # must not take the app with it. The connection is just marked lost.
    lost.add(dpy or 0)


_io_handler = _IOExitHandler(_on_io_exit)
_IOErrorHandler = ctypes.CFUNCTYPE(c_int, c_void_p)


def _on_io_error(dpy):
    lost.add(dpy or 0)   # the default prints "XIO: fatal IO error" and exits
    return 0


_io_error = _IOErrorHandler(_on_io_error)


def lib():
    """libX11, set up once; None without one (or without a DISPLAY)."""
    global _lib
    with _lib_lock:
        if _lib is None:
            name = ctypes.util.find_library("X11") or "libX11.so.6"
            try:
                x = ctypes.CDLL(name)
            except OSError:
                _lib = False
                return None
            x.XOpenDisplay.restype = c_void_p
            x.XOpenDisplay.argtypes = [c_char_p]
            x.XCloseDisplay.argtypes = [c_void_p]
            x.XDefaultRootWindow.restype = c_ulong
            x.XDefaultRootWindow.argtypes = [c_void_p]
            x.XKeysymToKeycode.restype = ctypes.c_ubyte
            x.XKeysymToKeycode.argtypes = [c_void_p, c_ulong]
            x.XkbKeycodeToKeysym.restype = c_ulong
            x.XkbKeycodeToKeysym.argtypes = [c_void_p, ctypes.c_ubyte, c_int, c_int]
            x.XGrabKey.argtypes = [c_void_p, c_int, c_uint, c_ulong, c_int, c_int, c_int]
            x.XUngrabKey.argtypes = [c_void_p, c_int, c_uint, c_ulong]
            x.XSync.argtypes = [c_void_p, c_int]
            x.XFlush.argtypes = [c_void_p]
            x.XPending.argtypes = [c_void_p]
            x.XNextEvent.argtypes = [c_void_p, POINTER(XEvent)]
            x.XConnectionNumber.argtypes = [c_void_p]
            x.XQueryKeymap.argtypes = [c_void_p, c_char * 32]
            x.XkbSetDetectableAutoRepeat.argtypes = [c_void_p, c_int, POINTER(c_int)]
            x.XUngrabKeyboard.argtypes = [c_void_p, c_ulong]
            x.XInternAtom.restype = c_ulong
            x.XInternAtom.argtypes = [c_void_p, c_char_p, c_int]
            x.XGetWindowProperty.argtypes = [
                c_void_p, c_ulong, c_ulong, c_long, c_long, c_int, c_ulong, POINTER(c_ulong),
                POINTER(c_int), POINTER(c_ulong), POINTER(c_ulong), POINTER(c_void_p)]
            x.XFree.argtypes = [c_void_p]
            x.XGetGeometry.argtypes = [c_void_p, c_ulong, POINTER(c_ulong), POINTER(c_int),
                                       POINTER(c_int), POINTER(c_uint), POINTER(c_uint),
                                       POINTER(c_uint), POINTER(c_uint)]
            x.XTranslateCoordinates.argtypes = [c_void_p, c_ulong, c_ulong, c_int, c_int,
                                                POINTER(c_int), POINTER(c_int),
                                                POINTER(c_ulong)]
            x.XSetErrorHandler.restype = c_void_p
            x.XSetErrorHandler.argtypes = [_ErrorHandler]
            x.XInitThreads()
            x.XSetErrorHandler(_handler)
            x.XSetIOErrorHandler.restype = c_void_p
            x.XSetIOErrorHandler.argtypes = [_IOErrorHandler]
            _set_io_exit = getattr(x, "XSetIOErrorExitHandler", None)   # libX11 1.7+
            if _set_io_exit is not None:
                _set_io_exit.argtypes = [c_void_p, _IOExitHandler, c_void_p]
                x.XSetIOErrorHandler(_io_error)   # only safe with an exit handler to follow
            _lib = x
        return _lib or None


def xtst():
    global _xtst
    with _lib_lock:
        if _xtst is None:
            try:
                t = ctypes.CDLL(ctypes.util.find_library("Xtst") or "libXtst.so.6")
                t.XTestFakeKeyEvent.argtypes = [c_void_p, c_uint, c_int, c_ulong]
                _xtst = t
            except OSError:
                _xtst = False
        return _xtst or None


def available() -> bool:
    return bool(os.environ.get("DISPLAY")) and lib() is not None


class Display:
    """One X connection (Xlib connections aren't shared across threads here: each
    user opens its own)."""

    def __init__(self):
        x = lib()
        self.x = x
        self.dpy = x.XOpenDisplay(None) if x is not None and os.environ.get("DISPLAY") else None
        if not self.dpy:
            raise OSError("no X display")
        if hasattr(x, "XSetIOErrorExitHandler"):
            x.XSetIOErrorExitHandler(self.dpy, _io_handler, None)
        self.root = x.XDefaultRootWindow(self.dpy)

    @property
    def alive(self) -> bool:
        return bool(self.dpy) and self.dpy not in lost

    def close(self):
        if self.dpy:
            if self.dpy not in lost:
                self.x.XCloseDisplay(self.dpy)
            self.dpy = None

    def keycode(self, vk: int) -> int:
        ks = vk_to_keysym(vk)
        return self.x.XKeysymToKeycode(self.dpy, ks) if ks is not None else 0

    def keysym(self, keycode: int, level: int = 0) -> int:
        return self.x.XkbKeycodeToKeysym(self.dpy, keycode, 0, level)

    def grab(self, keycode: int, mods: int) -> bool:
        """Grab keycode+mods (with every lock-key variant). False if another program
        already has it."""
        del _errors[:]
        for extra in _LOCK_VARIANTS:
            self.x.XGrabKey(self.dpy, keycode, mods | extra, self.root, 0,
                            GrabModeAsync, GrabModeAsync)
        self.x.XSync(self.dpy, 0)
        failed = BadAccess in _errors
        del _errors[:]
        if failed:
            self.ungrab(keycode, mods)
        return not failed

    def ungrab(self, keycode: int, mods: int):
        for extra in _LOCK_VARIANTS:
            self.x.XUngrabKey(self.dpy, keycode, mods | extra, self.root)
        self.x.XSync(self.dpy, 0)
        del _errors[:]

    def keymap(self) -> bytes:
        buf = (c_char * 32)()
        self.x.XQueryKeymap(self.dpy, buf)
        return bytes(buf)

    def fake_key(self, keycode: int, down: bool) -> bool:
        t = xtst()
        if t is None or not keycode:
            return False
        ok = t.XTestFakeKeyEvent(self.dpy, keycode, 1 if down else 0, 0)
        self.x.XFlush(self.dpy)
        return bool(ok)

    def ungrab_keyboard(self):
        """End the keyboard grab X starts when a grabbed key goes down, so the game
        still gets every other key while a hotkey is held."""
        self.x.XUngrabKeyboard(self.dpy, 0)   # CurrentTime
        self.x.XFlush(self.dpy)

    def pending(self) -> int:
        return self.x.XPending(self.dpy)

    def next_event(self) -> XEvent:
        ev = XEvent()
        self.x.XNextEvent(self.dpy, byref(ev))
        return ev

    def fileno(self) -> int:
        return self.x.XConnectionNumber(self.dpy)

    def cardinals(self, window: int, prop: str) -> list[int]:
        """A window's 32-bit property (CARDINAL / WINDOW, e.g. _NET_WM_PID) as numbers;
        [] when it has none (or the window is gone: the error handler takes BadWindow)."""
        atom = self.x.XInternAtom(self.dpy, prop.encode(), 1)
        if not atom:
            return []
        kind, fmt, n, after, data = c_ulong(), c_int(), c_ulong(), c_ulong(), c_void_p()
        if self.x.XGetWindowProperty(self.dpy, window, atom, 0, 64, 0, 0, byref(kind),
                                     byref(fmt), byref(n), byref(after), byref(data)) != 0:
            return []
        try:
            if fmt.value != 32 or not data.value:
                return []
            # format 32 comes back as C longs, whatever their size
            return [v & 0xFFFFFFFF for v in (c_long * n.value).from_address(data.value)]
        finally:
            if data.value:
                self.x.XFree(data)

    def window_rect(self, window: int) -> tuple[int, int, int, int] | None:
        """A window's (left, top, width, height) on the screen, in X's (native) pixels;
        None if it's gone."""
        root, x, y = c_ulong(), c_int(), c_int()
        w, h, border, depth = c_uint(), c_uint(), c_uint(), c_uint()
        if not self.x.XGetGeometry(self.dpy, window, byref(root), byref(x), byref(y),
                                   byref(w), byref(h), byref(border), byref(depth)):
            return None
        child = c_ulong()
        if not self.x.XTranslateCoordinates(self.dpy, window, self.root, 0, 0, byref(x),
                                            byref(y), byref(child)):
            return None
        return x.value, y.value, w.value, h.value

    def detectable_autorepeat(self):
        ok = c_int(0)
        self.x.XkbSetDetectableAutoRepeat(self.dpy, 1, byref(ok))
        return bool(ok.value)
