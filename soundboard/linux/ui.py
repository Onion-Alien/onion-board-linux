"""Linux behaviour for the main window's and the setup guide's cable buttons.

On Windows those download and run VB-Cable's installer (a permission prompt, often a
restart). On Linux the app makes the cable itself in a moment (soundboard.linux.
vcable): no download, so the "setup downloads" switch doesn't apply, no permission
prompt, no restart. "Game has no microphone setting?" sets the cable as the default
mic directly instead of walking the user through a control panel.

patch_main_window / patch_setup_wizard are called at the end of their modules,
before any window exists, so the buttons connect to these versions.
"""
from __future__ import annotations

import html
import logging

from soundboard.linux import vcable

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
    cls.install_cable = install_cable
    cls.open_windows_mic = open_windows_mic


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
