"""Linux side of soundboard.remote: the control API (and Onion Pocket's) listens again
at once after a restart.

Upstream turns SO_REUSEADDR off because on Windows it lets two programs share a port.
On Linux it never does that (a second listener still gets "address in use"); it only
lets a new listener bind while the old one's connections wait out TIME_WAIT. Without
it, a board restarted within about a minute of answering a request (a crash, Restart
to update, a quit and start) couldn't listen: Onion Pocket and Stream Deck buttons
went dead until the next start (found on Fedora)."""
from __future__ import annotations

import sys

__all__ = ["_Server"]


class _Server(sys.modules["soundboard.remote"]._Server):   # this runs at its end
    allow_reuse_address = True
