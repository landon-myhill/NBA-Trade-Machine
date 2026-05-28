from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.data.repository import get_repo
from app.fairness.engine import evaluate
from app.fairness.finder import find_packages
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
