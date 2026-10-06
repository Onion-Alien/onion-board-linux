"""conftest's closed_port(): connecting to it is refused at once (Windows' ~2 s
refusal skipped). The port number goes back to the system, which can hand it to a
server a later test starts: that server must be reachable, not refused forever (a
fake proxy's connection to the test's web server was refused that way and
test_net.py failed with "the proxy closed the connection", about one run in seven)."""
import socket

from conftest import closed_port


def test_a_closed_port_is_refused_at_once():
    port = closed_port()
    with socket.socket() as c:
        assert c.connect_ex(("127.0.0.1", port)) != 0


def test_a_server_given_a_port_once_taken_as_closed_is_reachable():
    port = closed_port()
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))      # what the system did for the later server
    srv.listen(1)
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5):
            pass
    finally:
        srv.close()
