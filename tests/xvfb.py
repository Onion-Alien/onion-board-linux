"""A private Xvfb for the Linux tests that need an X server."""
import os
import subprocess

import pytest


def start_xvfb(*args) -> tuple[subprocess.Popen, int]:
    """Xvfb on a display it picks itself (-displayfd): test workers running side by side
    (pytest-xdist) never end up on the same one."""
    r, w = os.pipe()
    proc = subprocess.Popen(["Xvfb", "-displayfd", str(w), "-nolisten", "tcp", *args],
                            pass_fds=(w,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.close(w)
    with os.fdopen(r) as f:
        line = f.readline().strip()   # written once it takes connections; "" if it died
    if not line.isdigit():
        proc.kill()
        pytest.fail("Xvfb didn't start")
    return proc, int(line)
