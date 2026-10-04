"""Linux side of soundboard.library: removed files go to the desktop's Trash (the
freedesktop.org one GNOME, KDE and the rest share), as they go to the Recycle Bin
on Windows."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

__all__ = ["recycle"]


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
