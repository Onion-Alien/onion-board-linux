"""Linux behaviour for the main window's and the setup guide's cable buttons.

On Windows those download and run VB-Cable's installer (a permission prompt, often a
restart). On Linux the app makes the cable itself in a moment (soundboard.linux.
vcable): no download, so the "setup downloads" switch doesn't apply, no permission
prompt, no restart. "Game has no microphone setting?" sets the cable as the default
mic directly instead of walking the user through a control panel. The Voice tab
never offers Windows' voice installs. The game watcher behind Who's listening's
suggestion runs on X11 too (linux/voicesdk.py). Settings has no switch for the
cable's download (there is none). The Triggers tab is hidden: Onion Watch has no Linux
version yet. The overlay's "the one the game is on" follows the game on X11, and its
preview lets clicks through as on Windows.

patch_main_window / patch_setup_wizard are called at the end of their modules,
before any window exists, so the buttons connect to these versions.
"""
from __future__ import annotations

import html
import logging
import sys

from soundboard.linux import audio, portal, vcable, x11

log = logging.getLogger(__name__)

MAKE = "✚  Make it now (free, no download)"
FAILED = ("Couldn't make the virtual cable: Onion Board needs PipeWire or PulseAudio, "
          "and their pactl tool (the pulseaudio-utils package). The log has the details.")
OUTPUTS_AFTER_MS = 800   # at start-up, the outputs open this long after the window is built
# the engine's output setters held back at start-up, and the name each one sets
_OUTPUT_SETTERS = ("set_main_device", "set_tap_device", "set_mon_device", "set_obs_device")
_KEYS = {"set_main_device": "main", "set_mon_device": "mon", "set_obs_device": "obs"}
_held: list | None = None   # (setter, device name) while the app's window is being built
# why keyboard hotkeys don't work everywhere (linux/keys.Hotkeys.why), in words, for
# the status line instead of upstream's "another program is already using"
_REMOTE = ("your desktop's own keyboard shortcuts can run Onion Board's remote control "
           "(Settings → Remote)")
HOTKEY_WORDS = {
    "no-portal": "Keyboard hotkeys can't work on this desktop: it doesn't let apps have "
                 "shortcuts. Pads and MIDI still work, and " + _REMOTE + ".",
    "x11-only": "Hotkeys only work while a game or another X11 app is in front: this "
                "desktop doesn't let apps have shortcuts everywhere. To use them anywhere, "
                + _REMOTE + ".",
    "declined": "Hotkeys are off: they weren't allowed when your desktop asked. Allow "
                "Onion Board's shortcuts in your desktop's keyboard settings.",
    "failed": "Your desktop didn't take Onion Board's hotkeys. Pads and MIDI still work, "
              "and " + _REMOTE + ".",
}


def _open_held(win, held):
    """The outputs held back while the window was built, opened now; one the user has
    set since (the setup guide, Settings) is theirs and stays."""
    if win._shut_down:
        return
    e = win.engine
    for n, name in held:
        key = _KEYS.get(n)
        if (e.names.get(key) if key else getattr(e, "tap_name", None)) is None:
            getattr(e, n)(name)
    win._update_status()


def describe_action(win, action: str) -> str:
    """A hotkey action as Settings words it ("Stop everything"), a sound as "Play
    <its name>", a category's random pick as "Random from <category>"."""
    from soundboard.settings import HOTKEY_ACTIONS
    from soundboard.ui.mainwindow import RANDOM
    for _attr, act, label, _desc in HOTKEY_ACTIONS:
        if act == action:
            return label
    if action.startswith(RANDOM):
        return f"Random from {action[len(RANDOM):]}"
    for m in win.cfg.sounds:
        if m.id == action:
            return f"Play {m.name}"
    return action


def patch_main_window(cls):
    orig_init = cls.__init__
    orig_init_devices = cls._init_devices
    orig_heard_device = cls._heard_device

    def __init__(self, *a, **k):
        global _held
        # the desktop's "allow these shortcuts?" list (Wayland portal) in words; set
        # first: the window registers its hotkeys while it's being built
        portal.describe = lambda action, win=self: describe_action(win, action)
        from soundboard.ui import splash
        # the app starting (its splash is up; not a test's window): the outputs open
        # once the window is up, see _init_devices
        _held = [] if splash._splash is not None else None
        try:
            orig_init(self, *a, **k)
        finally:
            held, _held = _held, None
        if held:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(OUTPUTS_AFTER_MS, self, lambda: _open_held(self, held))
        if getattr(self, "btn_install", None) is not None:
            self.btn_install.setText("Make the virtual cable")
        # no Triggers tab until Onion Watch, the add-on it holds, runs on Linux (it
        # captures the screen with Windows' own APIs); hidden, not removed, so
        # everything that looks the tab up still finds it
        ti = self.tabs.indexOf(self.triggers)
        self.tabs.setTabVisible(ti, False)
        if self.tabs.currentIndex() == ti:   # the last tab used, on Windows
            self.tabs.setCurrentIndex(0)
        from soundboard import appaudio, voicesdk
        from soundboard.ui import mainwindow
        # the game in front's voice engine (linux/voicesdk.py): needs X11 / XWayland
        if getattr(self, "voice_watch", 0) is None and x11.available():
            self.voice_watch = voicesdk.Watcher()
            self._voice_timer.start(mainwindow.VOICE_POLL_MS)
        # Who's listening: the program recording what the board sends, from PipeWire's
        # links (linux/appaudio.recording_apps); upstream only on Windows
        if getattr(self, "listeners", 0) is None and appaudio.supported()[0]:
            self.listeners = voicesdk.Listeners()
            self._cable_watch = voicesdk.Listeners()
            if not self._voice_timer.isActive():   # (a Wayland desktop: no game watcher)
                self._voice_timer.start(mainwindow.VOICE_POLL_MS)

    def _heard_device(self):
        """Straight into my mic: who records Onion Board's mic (Discord, games and
        browsers on Default do), and the cable's far end if there is one; upstream
        looks at the user's own mic, which carries the sounds only on Windows (here an
        app pinned to it hears the voice alone)."""
        if self.cfg.route != "mic":
            return orig_heard_device(self)
        from soundboard import directmic as dm
        from soundboard import engine as eng
        from soundboard.linux import directmic
        e = self.engine
        if e.main_stream is None or e.names.get("main") != dm.DEVICE:
            return None
        cables = [eng.virtual_mic_for(o) for o in eng.virtual_outputs()]
        return tuple(dict.fromkeys(d for d in (directmic.SOURCE_DESC, *cables) if d))

    def _cable_tip(self):
        """Upstream's tip, for Linux: the sounds are in Onion Board's mic (Default),
        not in the user's own mic, so that's where to point the app."""
        from soundboard import engine as eng
        from soundboard import voicesdk
        from soundboard.linux import directmic
        c = self.cfg
        watch = getattr(self, "_cable_watch", None)
        if c.cable_tip_done or self.engine.tap is None or watch is None:
            return
        apps = set(voicesdk.VOICE_APPS.values())
        heard = [h for h in watch.poll(eng.virtual_mic_for(self.engine.tap_name))
                 if h in apps]
        if heard:
            c.cable_tip_done = True
            self._save_now()
            self.toast(f"{heard[0][1]} still uses the virtual cable as its mic. It still "
                       "hears you, but you can set its input back to Default (or "
                       f"“{directmic.SOURCE_DESC}”): your sounds are in it now.")

    def install_cable(self):
        if vcable.install():
            self.refresh_devices()
            self.toast(f"✓ Made the virtual cable. In Discord or your game, pick "
                       f"“{vcable.SOURCE_DESC}” as the microphone.", "ok")
        else:
            self.toast(html.escape(FAILED), "warn")

    def open_windows_mic(self):
        if self.cfg.route == "mic":   # Onion Board's own mic is the default already
            from soundboard.linux import directmic
            if directmic.ensure():
                self.toast(f"✓ “{directmic.SOURCE_DESC}” is your default microphone: "
                           "restart the game.", "ok")
            else:
                self.toast("Couldn't make Onion Board's mic the default. Pick "
                           f"“{directmic.SOURCE_DESC}” as the input in the system's "
                           "Sound settings.", "warn")
            return
        if vcable.make_default_mic():
            self.toast(f"✓ “{vcable.SOURCE_DESC}” is now your default microphone: restart "
                       "the game. To undo, pick your own mic in the system's Sound "
                       "settings.", "ok")
        else:
            self.toast("Couldn't change the default microphone. Pick "
                       f"“{vcable.SOURCE_DESC}” as the input in the system's Sound "
                       "settings.", "warn")

    # straight into my mic (linux/directmic.py): Onion Board's mic only exists while
    # the board runs and sends into it; the user's own mic is the default again once
    # it's another route, or the board quits (a crash: the mic's holder shell)
    orig_set_route = cls.set_route
    orig_shutdown = cls.shutdown

    def set_route(self, route: str, device: str | None = None):
        orig_set_route(self, route, device)
        if self.cfg.route != "mic":
            from soundboard.linux import directmic
            directmic.release()

    def shutdown(self):
        orig_shutdown(self)
        from soundboard.linux import directmic
        directmic.release()

    def _init_devices(self):
        """At start-up the outputs (what others hear, the headphones, the stream output,
        the cable beside the mic) open a moment after the window is up, not while it's
        built: the window's first show and paint are Qt work that holds Python's lock
        for up to ~100 ms at a time on a slow PC (software OpenGL), and an output
        stream's callback can't run until it's let go: 2-5 drop-outs at every start on
        the Fedora VM, the status line telling a new user to pick safer buffering. The
        mic opens at once (it fills its own cushion first)."""
        if _held is None:
            return orig_init_devices(self)
        e = self.engine
        for n in _OUTPUT_SETTERS:   # this engine's calls only; the class's stay
            setattr(e, n, lambda name, _n=n: _held.append((_n, name)))
        try:
            orig_init_devices(self)
        finally:
            for n in _OUTPUT_SETTERS:
                e.__dict__.pop(n, None)

    orig_hotkeys_failed = cls.on_hotkeys_failed

    def on_hotkeys_failed(self, failed: list[str]):
        """Upstream says a failed key is another program's; on Linux the desktop may
        not let apps have hotkeys at all, or only while an X11 window is in front:
        say that instead (the X11-only note once a session)."""
        why = getattr(self.hotkeys, "why", "")
        words = HOTKEY_WORDS.get(why)
        if words is None or (why == "x11-only" and getattr(self, "_x11_only_told", False)):
            return orig_hotkeys_failed(self, failed)
        if why != "x11-only" and not failed:
            return
        self._x11_only_told = True
        from soundboard import theme
        log.warning("keyboard hotkeys (%s): %s", why, failed)
        self.status.setText(f"<span style='color:{theme.status('warn')}'>"
                            f"{html.escape(words)}</span>")

    cls.on_hotkeys_failed = on_hotkeys_failed
    cls.__init__ = __init__
    cls._init_devices = _init_devices
    cls._heard_device = _heard_device
    cls._cable_tip = _cable_tip
    cls.set_route = set_route
    cls.shutdown = shutdown
    mw = sys.modules[cls.__module__]
    # picking a Bluetooth headset's mic warns about call quality: Linux doesn't name
    # it "Hands-Free", the sound server's name for it says Bluetooth
    upstream_hands_free = mw.is_hands_free
    mw.is_hands_free = lambda name: upstream_hands_free(name) or audio.bluetooth_mic(name)
    # upstream starts load_triggers' timer while the window is being built and the
    # splash's pump runs pending events before __init__ sets _shut_down: on a slow
    # PC the timer fired first (AttributeError at every start on the Fedora VM)
    cls._shut_down = False
    # ...and it never asks for attention (triggers brought over from Windows)
    cls._nudge_triggers = lambda self, index: None
    cls.install_cable = install_cable
    cls.open_windows_mic = open_windows_mic
    from soundboard.ui.voicepanel import SpeechPanel
    patch_speech_panel(SpeechPanel)
    from soundboard.ui.overlay import OverlayWindow
    patch_overlay(OverlayWindow)


def patch_overlay(cls):
    """"The one the game is on" follows the game on X11 too: upstream asks only on
    Windows; linux/keys.py's foreground_monitor_info finds the window in front."""
    orig_screen = cls._screen

    def _screen(self, follow_game: bool):
        from PySide6.QtGui import QGuiApplication
        from soundboard import winkeys
        from soundboard.ui import overlay
        if follow_game and self.ov.s.monitor == overlay.MONITOR_GAME \
                and QGuiApplication.platformName() == "xcb":
            name, rect = winkeys.foreground_monitor_info()
            sc = overlay.pick_screen(QGuiApplication.screens(), name, rect)
            if sc is not None:
                return sc
        return orig_screen(self, follow_game)

    cls._screen = _screen
    from soundboard.ui.overlay import Overlay
    patch_overlay_preview(Overlay)


def patch_overlay_preview(cls):
    """Show preview lets clicks through to what's under it while it's up (it's only
    to look at); upstream does that with a Windows window style. Here it's Qt's own
    flag on the window: an empty input shape on X11, an empty input region on
    Wayland."""
    orig = cls._set_previewing

    def _set_previewing(self, on: bool):
        from PySide6.QtCore import Qt
        orig(self, on)
        w = self._window
        h = w.windowHandle() if w is not None else None
        if h is not None:
            h.setFlag(Qt.WindowTransparentForInput, self._previewing)

    cls._set_previewing = _set_previewing


def patch_speech_panel(cls):
    """The Voice tab's translation box: when the voice for a language is missing,
    Windows offers an Install button (Windows Update) and a Windows settings button.
    eSpeak's voices come with the distribution's package: say so, keep Reload."""
    orig_refresh = cls._refresh_translation

    def _refresh_translation(self):
        orig_refresh(self)
        if self.b_voice_install.isHidden():
            return
        self.b_voice_install.hide()
        self.b_voices.hide()
        m = self._lang()
        name = (m.language_name or m.language) if m is not None else "this language"
        self.lbl_tr.setText(f"\u26a0 There's no {name} voice here yet, so {name} can't be "
                            "spoken properly. Install your distribution's espeak-ng "
                            "package (or put a Piper voice in your voices folder), then "
                            "press Reload voices.")

    cls._refresh_translation = _refresh_translation


def patch_setup_wizard(cls):
    orig_recheck = cls.recheck_cable

    def recheck_cable(self, rescan: bool = True):
        orig_recheck(self, rescan)
        # nothing is downloaded: the switch for setup downloads doesn't apply
        self.btn_cable.setEnabled(True)
        self.btn_cable.setToolTip("")
        if self.btn_cable.text().startswith("⬇"):
            self.btn_cable.setText(MAKE)
        self.btn_restart.hide()   # never needed on Linux

    def install_cable(self):
        # on the mic route this is "Use the virtual cable instead", as upstream's
        if self.win.cfg.route == "mic" and self.cable_ok():   # there already: just switch
            self._pick_route("cable")
            return
        if self.win.cfg.route == "mic":
            self.win.set_route("cable")
        if vcable.install():
            self.recheck_cable(rescan=True)
        else:
            from soundboard.ui.setupwizard import _bad
            self.cable_status.setText(f"<span style='color:{_bad()}'>{html.escape(FAILED)}"
                                      "</span>")

    cls.recheck_cable = recheck_cable
    cls.install_cable = install_cable
    # Windows' RunOnce entry that reopens the guide after the cable's restart: no
    # restart here, and no registry
    from soundboard.ui import setupwizard
    setupwizard.resume_after_restart = lambda on: None


def _hide_option(box):
    """Hide a Settings checkbox and its explanation (the next widget in its layout)."""
    def find(layout):
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget() is box:
                return layout, i
            if item.layout() is not None and (hit := find(item.layout())):
                return hit
        return None
    parent = box.parentWidget()
    hit = find(parent.layout()) if parent is not None and parent.layout() else None
    box.hide()
    if hit:
        layout, i = hit
        nxt = layout.itemAt(i + 1)
        if nxt is not None and nxt.widget() is not None:
            nxt.widget().hide()


def patch_settings(cls):
    """Privacy & security: no "Virtual cable download" switch, the app makes its own
    cable and downloads nothing for it. Add-ons & help: no Onion Watch card (there's
    no Triggers tab on Linux)."""
    orig_switches = cls._switches_card

    def _switches_card(self):
        card = orig_switches(self)
        if (box := self.net_boxes.get("setup_downloads")) is not None:
            _hide_option(box)
        return card

    cls._switches_card = _switches_card
    orig_addons = cls._addons_card

    def _addons_card(self):   # Onion Watch: the Triggers tab's, hidden (patch_main_window)
        card = orig_addons(self)
        card.hide()
        return card

    cls._addons_card = _addons_card
    orig_hotkeys = cls._hotkeys

    def _hotkeys(self):
        """Hotkeys: when the desktop doesn't let them work everywhere, say so on top
        (the status line's note is soon replaced by the next message)."""
        w = orig_hotkeys(self)
        words = HOTKEY_WORDS.get(getattr(getattr(self.mw, "hotkeys", None), "why", ""))
        if words:
            from PySide6.QtWidgets import QLabel

            from soundboard import theme
            note = QLabel(words)
            note.setObjectName("hotkeyslimit")
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {theme.status('warn')};")
            note.setContentsMargins(14, 0, 14, 0)   # in line with the cards' text
            w.layout().insertWidget(0, note)
        return w

    cls._hotkeys = _hotkeys
