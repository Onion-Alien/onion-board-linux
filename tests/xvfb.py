"""A private Xvfb for the Linux tests that need an X server."""
import os
import select
import subprocess

import pytest

SOCKETS = "/tmp/.X11-unix"   # where every X server makes its socket


def start_xvfb(*args, wait: float = 20.0) -> tuple[subprocess.Popen, int]:
    """Xvfb on a display it picks itself (-displayfd): test workers running side by side
    (pytest-xdist) never end up on the same one.

    Fails at once, saying why, where Xvfb can't make its socket (WSLg mounts the
    socket folder read-only: Xvfb then tries one display after another forever),
    and after `wait` seconds if it hasn't started."""
    if os.path.isdir(SOCKETS) and not os.access(SOCKETS, os.W_OK):
        pytest.fail(f"{SOCKETS} is read-only (WSLg mounts it so): Xvfb can't make its "
                    "socket. Run the tests with a tmpfs there (docs/LINUX-PORT.md, "
                    "Running the tests here)")
    r, w = os.pipe()
    proc = subprocess.Popen(["Xvfb", "-displayfd", str(w), "-nolisten", "tcp", *args],
                            pass_fds=(w,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.close(w)
    with os.fdopen(r) as f:
        ready, _, _ = select.select([f], [], [], wait)
        # written once it takes connections; "" if it died
        line = f.readline().strip() if ready else ""
    if not line.isdigit():
        proc.kill()
        proc.wait()
        pytest.fail("Xvfb didn't start" if ready else f"Xvfb didn't start in {wait:.0f} s")
    return proc, int(line)
