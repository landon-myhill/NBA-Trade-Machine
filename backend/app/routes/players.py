from flask import Blueprint, abort, jsonify

from app.data.repository import get_repo
from app.fairness.contract_value import contract_adjustment
from app.fairness.multi_year import avg_field, trend_ratio
from app.fairness.stats_value import stats_value, value_components
from app.fairness.tier import assign_tier, tier_multiplier

bp = Blueprint("players", __name__, url_prefix="/api/players")


@bp.get("")
def list_players():
    return jsonify([p.model_dump() for p in get_repo().list_players()])


@bp.get("/ranked")
def ranked_players():
    """All players sorted by trade value (no fit bonus). Includes rank + TVS components."""
    repo = get_repo()
    rubric = repo.get_rubric()
    out = []
    for p in repo.list_players():
        sv = stats_value(p)
        tier, label = assign_tier(p, rubric)
        mult = tier_multiplier(tier, rubric)
        health_adjusted = sv * p.injury_discount
        tier_adjusted = health_adjusted * mult
        contract_adj = contract_adjustment(p, tier_adjusted, tier=tier)
        total = tier_adjusted + contract_adj
        out.append(
            {
                "id": p.id,
                "name": p.name,
                "team_id": p.team_id,
                "position": p.position,
                "age": p.age,
                "archetype": p.archetype,
                "tier": tier,
                "tier_label": label,
                "tier_multiplier": mult,
                "stats_value": round(sv, 1),
                "injury_discount": p.injury_discount,
                "tier_adjusted": round(tier_adjusted, 1),
                "contract_adjustment": round(contract_adj, 1),
                "current_salary": p.contract.current_salary,
                "years_remaining": p.contract.years_remaining,
                "total_value": round(total, 1),
                "bpm": p.stats.bpm,
                "vorp": p.stats.vorp,
                "bpm_2yr": round(avg_field(p.season_logs, "bpm", 2), 2),
                "bpm_5yr": round(avg_field(p.season_logs, "bpm", 5), 2),
                "trend_ratio": round(trend_ratio(p.season_logs, "bpm"), 2),
            }
        )
    out.sort(key=lambda x: -x["total_value"])
    for i, p in enumerate(out):
        p["rank"] = i + 1
    return jsonify(out)


@bp.get("/<player_id>/breakdown")
def player_breakdown(player_id: str):
    """Full 'why this rating' decomposition for the player detail view."""
    repo = get_repo()
    p = repo.get_player(player_id)
    if not p:
        abort(404, f"Player {player_id} not found")
    rubric = repo.get_rubric()
    comps = value_components(p)
    sv = comps["stats_value"]
    tier, label = assign_tier(p, rubric)
    mult = tier_multiplier(tier, rubric)
    tier_adjusted = sv * p.injury_discount * mult
    cadj = contract_adjustment(p, tier_adjusted, tier=tier)
    total = tier_adjusted + cadj
    return jsonify(
        {
            "id": p.id,
            "name": p.name,
            "team_id": p.team_id,
            "position": p.position,
            "age": p.age,
            "archetype": p.archetype,
            "tier": tier,
            "tier_label": label,
            "tier_multiplier": mult,
            "injury_discount": p.injury_discount,
            "components": comps,
            "tier_adjusted": round(tier_adjusted, 1),
            "contract_adjustment": round(cadj, 1),
            "current_salary": p.contract.current_salary,
            "total_guaranteed": p.contract.total_guaranteed,
            "years_remaining": p.contract.years_remaining,
            "total_value": round(total, 1),
            "stats": p.stats.model_dump(),
            "season_logs": [log.model_dump() for log in p.season_logs],
            "trend_ratio": round(trend_ratio(p.season_logs, "bpm"), 2),
        }
    )


@bp.get("/<player_id>")
def get_player(player_id: str):
    player = get_repo().get_player(player_id)
    if not player:
        abort(404, f"Player {player_id} not found")
    return jsonify(player.model_dump())
