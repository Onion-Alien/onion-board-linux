"""Linux: the control API listens again at once after a restart (soundboard/linux/
remote.py), while two boards still can't share the port (test_remote.py's
test_a_taken_port_is_reported)."""
import sys
import urllib.request

import pytest

from soundboard import remote

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux only")
TOKEN = "t" * 32


def test_a_restart_right_after_a_request_can_listen_again(qapp):
    """The answered request's connection waits out TIME_WAIT on the server's side for
    about a minute; without SO_REUSEADDR the restarted board couldn't listen (Onion
    Pocket and Stream Deck dead until the next start: found on Fedora)."""
    c = remote.RemoteControl(lambda a, p: (200, {}))
    assert c.start(0, TOKEN)
    port = c.port
    try:
        with urllib.request.urlopen(f"http://{remote.HOST}:{port}/api/status?token={TOKEN}",
                                    timeout=5) as r:
            r.read()
    except Exception:  # noqa: BLE001 - any answer will do: the connection is what counts
        pass
    c.stop()
    again = remote.RemoteControl(lambda a, p: (200, {}))
    try:
        assert again.start(port, TOKEN), again.error
    finally:
        again.stop()
