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

    def __init__(self, *a, **k):
        # the desktop's "allow these shortcuts?" list (Wayland portal) in words; set
        # first: the window registers its hotkeys while it's being built
        portal.describe = lambda action, win=self: describe_action(win, action)
        orig_init(self, *a, **k)
        if getattr(self, "btn_install", None) is not None:
            self.btn_install.setText("Make the virtual cable")
        # no Triggers tab until Onion Watch, the add-on it holds, runs on Linux (it
        # captures the screen with Windows' own APIs); hidden, not removed, so
        # everything that looks the tab up still finds it
        ti = self.tabs.indexOf(self.triggers)
        self.tabs.setTabVisible(ti, False)
        if self.tabs.currentIndex() == ti:   # the last tab used, on Windows
            self.tabs.setCurrentIndex(0)
        # the game in front's voice engine (linux/voicesdk.py): needs X11 / XWayland
        if getattr(self, "voice_watch", 0) is None and x11.available():
            from soundboard import voicesdk
            from soundboard.ui import mainwindow
            self.voice_watch = voicesdk.Watcher()
            self._voice_timer.start(mainwindow.VOICE_POLL_MS)

    def install_cable(self):
        if vcable.install():
            self.refresh_devices()
            self.toast(f"✓ Made the virtual cable. In Discord or your game, pick "
                       f"“{vcable.SOURCE_DESC}” as the microphone.", "ok")
        else:
            self.toast(html.escape(FAILED), "warn")

    def open_windows_mic(self):
        if vcable.make_default_mic():
            self.toast(f"✓ “{vcable.SOURCE_DESC}” is now your default microphone: restart "
                       "the game. To undo, pick your own mic in the system's Sound "
                       "settings.", "ok")
        else:
            self.toast("Couldn't change the default microphone. Pick "
                       f"“{vcable.SOURCE_DESC}” as the input in the system's Sound "
                       "settings.", "warn")

    orig_flow = cls._update_flow

    def _update_flow(self, talking=False):
        orig_flow(self, talking)
        self.btn_attach.hide()   # "Straight into my mic instead": not on Linux yet

    cls.__init__ = __init__
    cls._update_flow = _update_flow
    # "Straight into my mic" isn't on Linux yet (linux/directmic.py): Setup -> Devices
    # doesn't offer it, and What's new doesn't tell about it
    mw = sys.modules[cls.__module__]
    mw.ROUTE_CHOICES = tuple(c for c in mw.ROUTE_CHOICES if c[1] != "mic")
    from soundboard.ui import whatsnew
    whatsnew.NOTES = without_direct_mic(whatsnew.NOTES)
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


def without_direct_mic(notes):
    """What's new without "Straight into my mic": 1.9.1's note is only about it; 1.9.0
    keeps what Linux has too (the simpler modes, the lag fixes)."""
    from dataclasses import replace
    out = []
    for n in notes:
        if n.version == "1.9.1":
            continue
        if n.version == "1.9.0":
            n = replace(n, headline="Simpler and smoother",
                        items=tuple(i for i in n.items if i[0] == "check"))
        out.append(n)
    return tuple(out)


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
        self.btn_attach.hide()   # straight into the mic: not on Linux yet
        # nothing is downloaded: the switch for setup downloads doesn't apply
        self.btn_cable.setEnabled(True)
        self.btn_cable.setToolTip("")
        if self.btn_cable.text().startswith("⬇"):
            self.btn_cable.setText(MAKE)
        self.btn_restart.hide()   # never needed on Linux

    def install_cable(self):
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
