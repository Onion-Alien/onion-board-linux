"""Linux side of soundboard.library: removed files go to the desktop's Trash (the
freedesktop.org one GNOME, KDE and the rest share), as they go to the Recycle Bin
on Windows. And the routes: no "Straight into my mic" yet, the cable is the way."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

__all__ = ["ROUTES", "recycle"]

# "Straight into my mic" isn't on Linux yet (linux/directmic.py): the routes the app
# offers and keeps. A saved "mic" (a new user's first start, the 1.9.1 move off the
# cable, settings brought over from Windows) is cleaned to the cable, as a newer
# version's route is, and the value as it was is still written back.
ROUTES = ("cable", "device", "off")


def _first_start_on_the_cable():
    """A new user starts on the cable (upstream: straight into the mic)."""
    from soundboard import library
    upstream = library.Config.first_start.__func__

    def first_start(cls):
        cfg = upstream(cls)
        if cfg.route not in ROUTES:
            cfg.route = "cable"
        return cfg
    library.Config.first_start = classmethod(first_start)


def recycle(path: Path) -> bool:
    """Send a file to the Trash (so it can still be restored from there). False if
    that isn't possible: the caller deletes it instead."""
    if not path.exists():
        return False
    try:
        # Qt fails ("Bad file descriptor") when the home Trash doesn't exist yet, as
        # on an account nothing has been trashed from: make it (private, as the spec says)
        from soundboard.linux import data_home
        trash = Path(data_home()) / "Trash"
        for d in (trash, trash / "files", trash / "info"):
            d.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        log.debug("couldn't make the Trash folder", exc_info=True)
    try:
        from PySide6.QtCore import QFile
        return bool(QFile.moveToTrash(str(path))) and not path.exists()
    except Exception:  # noqa: BLE001
        log.debug("moving %s to the Trash failed", path, exc_info=True)
        return False


_first_start_on_the_cable()
