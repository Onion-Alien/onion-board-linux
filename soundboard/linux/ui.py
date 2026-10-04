"""Linux behaviour for the main window's and the setup guide's cable buttons.

On Windows those download and run VB-Cable's installer (a permission prompt, often a
restart). On Linux the app makes the cable itself in a moment (soundboard.linux.
vcable): no download, so the "setup downloads" switch doesn't apply, no permission
prompt, no restart. "Game has no microphone setting?" sets the cable as the default
mic directly instead of walking the user through a control panel. The Voice tab
never offers Windows' voice installs. The game watcher behind Who's listening's
suggestion runs on X11 too (linux/voicesdk.py). Settings has no switch for the
cable's download (there is none). The Triggers tab is hidden: Onion Watch has no Linux
version yet. The overlay's "the one the game is on" follows the game on X11.

patch_main_window / patch_setup_wizard are called at the end of their modules,
before any window exists, so the buttons connect to these versions.
"""
from __future__ import annotations

import html
import logging

from soundboard.linux import vcable, x11

log = logging.getLogger(__name__)

MAKE = "✚  Make it now (free, no download)"
FAILED = ("Couldn't make the virtual cable: Onion Board needs PipeWire or PulseAudio, "
          "and their pactl tool (the pulseaudio-utils package). The log has the details.")


def patch_main_window(cls):
    orig_init = cls.__init__

    def __init__(self, *a, **k):
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

    cls.__init__ = __init__
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
