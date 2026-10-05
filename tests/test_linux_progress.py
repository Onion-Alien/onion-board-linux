"""docs/LINUX-PROGRESS.md stays readable by scripts/linux_progress.py."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "linux_progress.py"


def _load():
    spec = importlib.util.spec_from_file_location("linux_progress", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_item_parses_with_a_known_status_and_a_unique_id():
    mod = _load()
    rows = mod.items(mod.DOC.read_text(encoding="utf-8"))
    keys = [r[0] for r in rows]
    assert len(keys) == len(set(keys))
    assert all(1 <= r[2] <= 6 for r in rows)
    assert 0 < mod.estimate(rows) < 100


def test_half_counts_half_and_open_nothing():
    mod = _load()
    rows = [("a", "A", 2, "done"), ("b", "B", 2, "half"), ("c", "C", 4, "open")]
    assert mod.estimate(rows) == 37.5
