from flask import Blueprint, abort, jsonify

from app.cba.limits import TIER_LABEL, mle_amount
from app.cba.team_status import team_tax_tier, team_total_salary
from app.data.repository import get_repo
from app.fairness.contract_value import contract_adjustment
from app.fairness.stats_value import stats_value
from app.fairness.tier import assign_tier, tier_multiplier
from app.models import Player

bp = Blueprint("teams", __name__, url_prefix="/api/teams")


def _enrich_player(p: Player, rubric) -> dict:
    """Player JSON with total_value (TVS) attached for UI display."""
    sv = stats_value(p)
    tier, _ = assign_tier(p, rubric)
    mult = tier_multiplier(tier, rubric)
    health = sv * p.injury_discount
    tier_adj = health * mult
    cadj = contract_adjustment(p, tier_adj, tier=tier)
    data = p.model_dump()
    data["total_value"] = round(tier_adj + cadj, 1)
    return data


@bp.get("")
def list_teams():
    return jsonify([t.model_dump() for t in get_repo().list_teams()])


@bp.get("/<team_id>")
def get_team(team_id: str):
    team = get_repo().get_team(team_id)
    if not team:
        abort(404, f"Team {team_id} not found")
    return jsonify(team.model_dump())


@bp.get("/<team_id>/roster")
def get_roster(team_id: str):
    repo = get_repo()
    if not repo.get_team(team_id):
        abort(404, f"Team {team_id} not found")
    rubric = repo.get_rubric()
    roster = [p for p in repo.list_players() if p.team_id == team_id]
    return jsonify([_enrich_player(p, rubric) for p in roster])


@bp.get("/<team_id>/picks")
def get_picks(team_id: str):
    repo = get_repo()
    if not repo.get_team(team_id):
        abort(404, f"Team {team_id} not found")
    picks = [p for p in repo.list_picks() if p.owner_team_id == team_id]
    return jsonify([p.model_dump() for p in picks])


@bp.get("/payrolls")
def get_all_payrolls():
    """Bulk payroll snapshot for every team. Used by the Finder to annotate
    suggestion rows with each team's tax tier + payroll without N round-trips.
    """
    repo = get_repo()
    out = []
    for team in repo.list_teams():
        tier = team_tax_tier(team.id, repo)
        out.append(
            {
                "team_id": team.id,
                "total_salary": team_total_salary(team.id, repo),
                "tax_tier": tier,
                "tax_tier_label": TIER_LABEL[tier],
                "mle_amount": mle_amount(tier),
                "trade_exceptions": [e.model_dump() for e in team.trade_exceptions],
            }
        )
    return jsonify(out)


@bp.get("/<team_id>/payroll")
def get_payroll(team_id: str):
    """Lightweight payroll snapshot for showing context before any trade work.

    Returns total salary, current tax tier, the team's stored TPEs, and the
    MLE capacity available at this tier (0 for second-apron teams).
    """
    repo = get_repo()
    team = repo.get_team(team_id)
    if not team:
        abort(404, f"Team {team_id} not found")
    tier = team_tax_tier(team_id, repo)
    return jsonify(
        {
            "team_id": team_id,
            "total_salary": team_total_salary(team_id, repo),
            "tax_tier": tier,
            "tax_tier_label": TIER_LABEL[tier],
            "mle_amount": mle_amount(tier),
            "trade_exceptions": [e.model_dump() for e in team.trade_exceptions],
        }
    )
