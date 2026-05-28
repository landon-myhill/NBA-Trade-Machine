from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.data.repository import get_repo
from app.fairness.engine import evaluate
from app.fairness.finder import find_balancing_additions, find_packages
from app.models import Trade

bp = Blueprint("trades", __name__, url_prefix="/api/trades")


@bp.post("/evaluate")
def evaluate_trade():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    try:
        trade = Trade.model_validate(payload)
    except ValidationError as e:
        return jsonify({"error": "Invalid trade payload", "details": e.errors()}), 400

    try:
        report = evaluate(trade, get_repo())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(report.model_dump())


@bp.get("/find")
def find_trade():
    """Suggest fair + CBA-legal packages for an acquiring team to land a target.

    Query params: target=<player_id>, team=<acquiring_team_id>
    """
    target = request.args.get("target")
    team = request.args.get("team")
    if not target or not team:
        return jsonify({"error": "target and team query params required"}), 400
    try:
        result = find_packages(target, team, get_repo())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(result)


@bp.post("/find-balanced")
def find_balanced():
    """Anchored two-sided finder.

    Body:
      {
        "team_a_id": "...", "team_b_id": "...",
        "anchors_a": [{"player_id": "..."} | {"pick_id": "..."}],
        "anchors_b": [...],
        "max_additions": 2  (optional)
      }
    """
    payload = request.get_json(silent=True) or {}
    team_a_id = payload.get("team_a_id")
    team_b_id = payload.get("team_b_id")  # optional — None triggers league-wide search
    if not team_a_id:
        return jsonify({"error": "team_a_id is required"}), 400
    picks_round = payload.get("picks_round")
    fair_gap = payload.get("fair_gap_threshold")
    try:
        result = find_balancing_additions(
            team_a_id=team_a_id,
            team_b_id=team_b_id or None,
            anchors_a=payload.get("anchors_a", []) or [],
            anchors_b=payload.get("anchors_b", []) or [],
            repo=get_repo(),
            max_additions=int(payload.get("max_additions", 2)),
            return_preferences=payload.get("return_preferences") or [],
            picks_min_count=int(payload.get("picks_min_count", 1)),
            picks_years=payload.get("picks_years") or [],
            picks_round=int(picks_round) if picks_round else None,
            excluded_player_ids=payload.get("excluded_player_ids") or [],
            fair_gap_threshold=float(fair_gap) if fair_gap is not None else 0.15,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(result)
