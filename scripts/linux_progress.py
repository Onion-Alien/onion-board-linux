"""How complete the Linux port is, from the table in docs/LINUX-PROGRESS.md.

    python scripts/linux_progress.py              # the estimate and what's left
    python scripts/linux_progress.py --log "..."  # also adds a History line

Each item counts its weight when done, half of it when half done, nothing when open.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

DOC = Path(__file__).resolve().parent.parent / "docs" / "LINUX-PROGRESS.md"
CREDIT = {"done": 1.0, "half": 0.5, "open": 0.0}
ROW = re.compile(r"^\|\s*([a-z0-9-]+)\s*\|(.+?)\|\s*(\d+)\s*\|\s*(\w+)\s*\|\s*$")


def items(text: str) -> list[tuple[str, str, int, str]]:
    found = []
    for line in text.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        key, name, weight, status = m.group(1), m.group(2).strip(), int(m.group(3)), m.group(4)
        if status not in CREDIT:
            raise SystemExit(f"{key}: status {status!r} isn't done / half / open")
        found.append((key, name, weight, status))
    if not found:
        raise SystemExit(f"no items found in {DOC}")
    return found


def estimate(rows) -> float:
    total = sum(w for _, _, w, _ in rows)
    return 100 * sum(w * CREDIT[s] for _, _, w, s in rows) / total


def last_logged(text: str) -> str | None:
    hits = re.findall(r"^\|\s*\d{4}-\d\d-\d\d\s*\|\s*(\d+%)\s*\|", text, re.M)
    return hits[-1] if hits else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log", metavar="CHANGE", help="add a History line with this note")
    args = ap.parse_args()

    text = DOC.read_text(encoding="utf-8")
    rows = items(text)
    pct = f"{estimate(rows):.0f}%"
    was = last_logged(text)
    print(f"Estimate: {pct}" + (f" (was {was})" if was else ""))
    left = sorted((r for r in rows if r[3] != "done"), key=lambda r: -r[2] * (1 - CREDIT[r[3]]))
    print(f"Left ({len(left)}), biggest first:")
    for key, name, weight, status in left:
        print(f"  {weight * (1 - CREDIT[status]):>4.1f}  {key}: {name} [{status}]")

    if args.log:
        note = args.log.replace("|", "/").strip()
        line = f"| {datetime.date.today().isoformat()} | {pct} | {note} |"
        with DOC.open("a", encoding="utf-8", newline="\n") as f:
            if not text.endswith("\n"):
                f.write("\n")
            f.write(line + "\n")
        print("Logged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
