"""Trade finder — given a target player and an acquiring team, suggest packages
that are both fair (within a TVS gap threshold) and CBA-legal.

Enumerates combinations of the acquiring team's players (+ optional picks) up to
`max_players` assets, scores each, and returns the best matches.
"""
from __future__ import annotations

from itertools import combinations

from app.cba.limits import TIER_LABEL
from app.cba.matching import max_incoming_salary
from app.cba.team_status import team_tax_tier
from app.data.repository import Repository
from app.fairness.contract_value import contract_adjustment
from app.fairness.pick_value import pick_value
from app.fairness.stats_value import stats_value
from app.fairness.tier import assign_tier, tier_multiplier
from app.models import Player

FAIR_GAP = 0.15  # package within 15% of target value counts as fair


def _player_tvs(player: Player, rubric) -> float:
    sv = stats_value(player)
    tier, _ = assign_tier(player, rubric)
    mult = tier_multiplier(tier, rubric)
    tier_adj = sv * player.injury_discount * mult
    return tier_adj + contract_adjustment(player, tier_adj, tier=tier)


def find_packages(
    target_player_id: str,
    acquiring_team_id: str,
    repo: Repository,
    max_players: int = 3,
    max_picks: int = 2,
    include_picks: bool = True,
    limit: int = 15,
) -> dict:
    rubric = repo.get_rubric()
    target = repo.get_player(target_player_id)
    if not target:
        raise ValueError(f"Unknown target player: {target_player_id}")
    if not repo.get_team(acquiring_team_id):
        raise ValueError(f"Unknown team: {acquiring_team_id}")

    target_tvs = _player_tvs(target, rubric)
    target_salary = target.contract.current_salary
    seller_team = target.team_id

    # Acquiring team's tradeable assets
    players = [p for p in repo.list_players() if p.team_id == acquiring_team_id]
    picks = (
        [pk for pk in repo.list_picks() if pk.owner_team_id == acquiring_team_id]
        if include_picks
        else []
    )

    player_tvs = {p.id: _player_tvs(p, rubric) for p in players}
    pick_tvs = {pk.id: pick_value(pk) for pk in picks}

    acquirer_tier = team_tax_tier(acquiring_team_id, repo)

    # Pre-enumerate pick combos (0..max_picks) with their summed value
    pick_combos: list[tuple[tuple, float]] = [((), 0.0)]
    for k in range(1, max_picks + 1):
        for pcombo in combinations(picks, k):
            pick_combos.append((pcombo, sum(pick_tvs[pk.id] for pk in pcombo)))

    results = []
    # Player combos of size 0..max_players × pick combos; skip the empty package
    for n in range(0, max_players + 1):
        for combo in combinations(players, n):
            base_tvs = sum(player_tvs[p.id] for p in combo)
            salary_out = sum(p.contract.current_salary for p in combo)
            for pcombo, pcombo_tvs in pick_combos:
                if not combo and not pcombo:
                    continue
                total_tvs = base_tvs + pcombo_tvs
                gap = abs(total_tvs - target_tvs) / max(target_tvs, 1.0)
                if gap > FAIR_GAP:
                    continue
                max_in = max_incoming_salary(salary_out, acquirer_tier)
                legal = target_salary <= max_in
                if acquirer_tier == "second_apron" and len(combo) > 1:
                    legal = False
                # Pick-only or pick-heavy deals still need salary to match if a
                # player is incoming — picks carry $0, so salary_out must cover it.
                assets = [
                    {"kind": "player", "id": p.id, "name": p.name, "tvs": round(player_tvs[p.id], 1)}
                    for p in combo
                ]
                for pk in pcombo:
                    assets.append(
                        {
                            "kind": "pick",
                            "id": pk.id,
                            "name": f"{pk.year} R{pk.round} (#{int(pk.expected_pick)})"
                            + (f" [{pk.protections}]" if pk.protections else ""),
                            "tvs": round(pick_tvs[pk.id], 1),
                        }
                    )
                results.append(
                    {
                        "assets": assets,
                        "package_tvs": round(total_tvs, 1),
                        "gap_pct": round(gap * 100, 1),
                        "salary_out": salary_out,
                        "salary_in": target_salary,
                        "max_salary_in": max_in,
                        "cba_legal": legal,
                        "n_assets": len(assets),
                    }
                )

    # Prefer legal, then FEWEST assets (cleaner deals), then closest gap.
    # Fewest-first stops 3-player fine-tuned packages from dominating the list.
    results.sort(key=lambda r: (not r["cba_legal"], r["n_assets"], r["gap_pct"]))
    return {
        "target": {
            "id": target.id,
            "name": target.name,
            "team_id": seller_team,
            "tvs": round(target_tvs, 1),
            "salary": target_salary,
        },
        "acquiring_team_id": acquiring_team_id,
        "acquirer_tax_tier": acquirer_tier,
        "acquirer_tax_tier_label": TIER_LABEL[acquirer_tier],
        "packages": results[:limit],
    }
