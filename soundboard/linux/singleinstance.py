"""Linux side of soundboard.singleinstance: the lock is an flock() on a file in the
runtime folder, which the kernel frees if the app crashes (like the Windows named
mutex). The "come to the front" request still goes over the same QLocalSocket."""
from __future__ import annotations

import fcntl
import logging
import os
import tempfile
import time
from pathlib import Path

from PySide6.QtNetwork import QLocalSocket


log = logging.getLogger(__name__)

__all__ = ["claim_single_instance", "lock_path"]


def _si():
    """soundboard.singleinstance (it star-imports this module at its end)."""
    from soundboard import singleinstance
    return singleinstance


def lock_path() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or ""
    if not os.path.isdir(base):   # unset, or gone (seen on WSL): else no lock at all
        base = tempfile.gettempdir()
    uid = os.getuid() if hasattr(os, "getuid") else 0
    return Path(base) / f"{_si().INSTANCE_NAME}.{uid}.lock"


def claim_single_instance() -> bool:
    """True if we're the only Onion Board running. Otherwise asks the running one to
    come to the front and returns False."""
    try:
        fd = os.open(lock_path(), os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        log.warning("can't create the single-instance lock; carrying on", exc_info=True)
        return True
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
    else:
        claim_single_instance.fd = fd   # held until the process exits
        return True
    sock = QLocalSocket()
    deadline = time.monotonic() + _si().CONNECT_SECONDS
    while True:
        sock.connectToServer(_si().INSTANCE_NAME)
        if sock.waitForConnected(500) or time.monotonic() >= deadline:
            break
        sock.abort()
        time.sleep(0.2)
    if sock.state() == QLocalSocket.LocalSocketState.ConnectedState:
        sock.write(b"show")
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
    else:
        log.warning("the running Onion Board didn't answer: %s", sock.errorString())
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                None, "Onion Board is already running",
                "Onion Board is already open — look for its icon in the system tray."
                "\n\nIf you can't find it, run “pkill -f OnionBoard” and start it again.")
        except Exception:  # noqa: BLE001
            log.debug("couldn't show the already-running message", exc_info=True)
    return False
