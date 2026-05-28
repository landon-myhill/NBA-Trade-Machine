"""Recompute injury_discount for every player using the current constants.

Faster than re-running the full fetch — just reads current players.json,
recomputes discount from each player's season_logs + multi_year constants,
and writes back. Run after editing INJURY_MIN_DISCOUNT etc.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.fairness.multi_year import injury_discount  # noqa: E402

SEED_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "seed"
CURRENT_SEASON = "2025-26"


def main() -> None:
    path = SEED_DIR / "players.json"
    players = json.loads(path.read_text())
    changed = 0
    for p in players:
        logs = p.get("season_logs", [])
        new_disc = round(injury_discount(logs, CURRENT_SEASON), 2)
        if abs(new_disc - p.get("injury_discount", 1.0)) > 0.005:
            changed += 1
        p["injury_discount"] = new_disc
    path.write_text(json.dumps(players, indent=2))
    print(f"Updated injury_discount for {changed} of {len(players)} players")

    # Show samples
    samples = ["irvinky01", "halibty01", "lillada01", "vanvlfr01", "tatumja01"]
    for pid in samples:
        p = next((x for x in players if x["id"] == pid), None)
        if p:
            print(f"  {p['name']:<25} discount={p['injury_discount']:.2f}")


if __name__ == "__main__":
    main()
