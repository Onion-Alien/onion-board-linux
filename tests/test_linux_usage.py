"""Linux: the usage count tells Linux apart (soundboard/linux/usage.py). The daily
count goes to /app/linux/<version>, events end in /linux; the switch, the random ID
and what's sent are upstream's (tests/test_usage.py)."""
import sys

import pytest
from test_usage import _hits, sent  # noqa: F401 - fixture

from soundboard import __version__, net, usage
from soundboard.library import Config
from soundboard.linux import usage as lusage

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux only")


def test_the_daily_count_and_first_start_say_linux(sent):  # noqa: F811
    cfg = Config()
    usage.maybe_send(cfg)
    hits = _hits(sent[0][0])
    assert [h["path"] for h in hits] == [f"/app/linux/{__version__}", "first-start/linux"]
    assert hits[0]["title"] == f"Onion Board {__version__} (Linux)"
    assert hits[1]["title"] == "first-start/linux" and hits[1]["event"]
    assert {h["session"] for h in hits} == {cfg.stats_id}   # the one random ID
    assert all(set(h) <= {"path", "title", "event", "session"} for h in hits)
    cfg.stats_sent -= usage.EVERY_S
    usage.maybe_send(cfg)                       # the next day: no first-start again
    assert [h["path"] for h in _hits(sent[1][0])] == [f"/app/linux/{__version__}"]


def test_update_now_says_linux(sent):  # noqa: F811
    usage.maybe_send(Config(), event=usage.update_event("9.9.9"))
    (hit,) = _hits(sent[0][0])
    assert hit["path"] == hit["title"] == f"update-now/{__version__}-to-9.9.9/linux"


def test_switched_off_sends_nothing_on_linux_either(sent):  # noqa: F811
    cfg = Config()
    cfg.net_off = ["usage_stats"]
    net.configure_features(cfg.net_off)
    usage.maybe_send(cfg)
    assert sent == []


def test_off_the_paths_are_upstreams(sent, monkeypatch):  # noqa: F811
    """The hook off (as for upstream's own tests): Windows' paths, untouched."""
    monkeypatch.setattr(lusage, "active", False)
    usage.maybe_send(Config())
    assert [h["path"] for h in _hits(sent[0][0])] == [f"/app/{__version__}", "first-start"]
    assert usage.hits is lusage.hits            # the hook is what maybe_send calls
