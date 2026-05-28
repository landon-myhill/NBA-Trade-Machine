"""Derive each team's positional needs + competitive timeline and write to teams.json.

Needs: a position is a "need" if the team's best player there grades below
STARTER_TVS (no starting-caliber option).

Timeline: from 2025-26 win totals — contender (48+ W), rebuild (<28 W), else play_in.

    cd backend && python scripts/derive_team_context.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.repository import JsonRepository  # noqa: E402
from app.fairness.contract_value import contract_adjustment  # noqa: E402
from app.fairness.stats_value import stats_value  # noqa: E402
from app.fairness.tier import assign_tier, tier_multiplier  # noqa: E402
from generate_picks import fetch_standings  # noqa: E402

SEED_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "seed"
STARTER_TVS = 45.0  # below this at a position = a need
CONTENDER_WINS = 48
REBUILD_WINS = 28
POSITIONS = ["PG", "SG", "SF", "PF", "C"]


def _tvs(player, rubric) -> float:
    sv = stats_value(player)
    tier, _ = assign_tier(player, rubric)
    mult = tier_multiplier(tier, rubric)
    tier_adj = sv * player.injury_discount * mult
    return tier_adj + contract_adjustment(player, tier_adj, tier=tier)


def main() -> None:
    repo = JsonRepository()
    rubric = repo.get_rubric()

    # Best TVS per (team, position)
    best: dict[str, dict[str, float]] = {}
    for p in repo.list_players():
        tvs = _tvs(p, rubric)
        team = best.setdefault(p.team_id, {})
        team[p.position] = max(team.get(p.position, 0.0), tvs)

    print("Fetching standings for timeline…")
    standings = {abbr: wins for abbr, wins, _ in fetch_standings()}
    time.sleep(1)

    teams = json.loads((SEED_DIR / "teams.json").read_text())
    for t in teams:
        tid = t["id"]
        team_best = best.get(tid, {})
        needs = [
            pos for pos in POSITIONS if team_best.get(pos, 0.0) < STARTER_TVS
        ]
        wins = standings.get(tid, 41)
        if wins >= CONTENDER_WINS:
            timeline = "contender"
        elif wins < REBUILD_WINS:
            timeline = "rebuild"
        else:
            timeline = "play_in"
        t["needs"] = needs
        t["timeline"] = timeline

    (SEED_DIR / "teams.json").write_text(json.dumps(teams, indent=2))
    print(f"Updated needs + timeline for {len(teams)} teams")
    for t in teams:
        print(f"  {t['id']}: {t['timeline']:<10} needs={t['needs']}")


if __name__ == "__main__":
    main()
