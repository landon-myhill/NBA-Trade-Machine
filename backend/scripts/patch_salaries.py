"""Apply salary_overrides.json to players.json (instant, no re-scrape).

Run after editing salary_overrides.json to fix stale/wrong contract numbers.
"""
from __future__ import annotations

import json
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "seed"


def apply_overrides(players: list[dict]) -> int:
    ovr_path = SEED_DIR / "salary_overrides.json"
    if not ovr_path.exists():
        return 0
    overrides = json.loads(ovr_path.read_text()).get("overrides", {})
    by_id = {p["id"]: p for p in players}
    changed = 0
    for pid, fields in overrides.items():
        p = by_id.get(pid)
        if not p:
            continue
        contract = p.setdefault(
            "contract",
            {"current_salary": 0, "total_guaranteed": 0, "years_remaining": 0},
        )
        for key in ("current_salary", "total_guaranteed", "years_remaining"):
            if key in fields:
                contract[key] = fields[key]
        changed += 1
    return changed


def main() -> None:
    path = SEED_DIR / "players.json"
    players = json.loads(path.read_text())
    n = apply_overrides(players)
    path.write_text(json.dumps(players, indent=2))
    print(f"Applied salary overrides to {n} players")


if __name__ == "__main__":
    main()
