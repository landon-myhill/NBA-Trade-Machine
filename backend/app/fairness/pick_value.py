"""Draft pick value, on the same scale as player TVS.

    pick_value = base_curve(pick_number)
                 × rookie_premium    (1.20x for 1st rounders — team-friendly contract)
                 × class_strength    (per-year multiplier, default 1.0)
                 × future_discount   (0.97 ^ years_out)
                 × protection_factor

Calibrated so a clean #1 pick ≈ 50, top-3 picks ≈ Tier 2-3 player range, lottery
picks ≈ rotation player, late firsts ≈ deep bench, 2nd rounders are negligible.
"""
from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from app.models import DraftPick

CLASS_STRENGTH_PATH = Path(__file__).resolve().parent.parent / "data" / "seed" / "class_strength.json"

ROOKIE_DEAL_PREMIUM = 1.35  # bumped from 1.20 — picks worth a bit more vs players
FUTURE_DISCOUNT_RATE = 0.97


@lru_cache(maxsize=1)
def _class_strengths() -> dict[int, float]:
    raw = json.loads(CLASS_STRENGTH_PATH.read_text())
    return {int(k): float(v) for k, v in raw.items() if k.isdigit()}


def _base_curve(expected_pick: float, round_: int) -> float:
    if round_ == 2:
        if expected_pick >= 55:
            return 0.6
        if expected_pick >= 45:
            return 1.2
        return 2.2
    p = max(1.0, min(60.0, expected_pick))
    if p <= 3:
        return 50.0 - 3.0 * (p - 1)        # 50, 47, 44
    if p <= 7:
        return 44.0 - 4.0 * (p - 3)        # 40, 36, 32, 28
    if p <= 14:
        return 28.0 - 1.6 * (p - 7)        # 26.4 -> 16.8 (lottery cliff)
    if p <= 20:
        return 16.8 - 1.0 * (p - 14)       # 15.8 -> 10.8
    if p <= 30:
        return 10.8 - 0.6 * (p - 20)       # 10.2 -> 4.8
    return 4.0


def _future_discount(year: int, current_year: int | None = None) -> float:
    if current_year is None:
        current_year = datetime.now().year
    years_out = max(0, year - current_year)
    return FUTURE_DISCOUNT_RATE**years_out


def _parse_protection_threshold(protections: str) -> int | None:
    """Extract the protection band number, e.g. 'top-2 protected' -> 2."""
    p = protections.lower()
    if "lottery" in p:
        return 14
    for n in (14, 10, 8, 5, 4, 3, 2, 1):
        if f"top-{n}" in p or f"top {n}" in p:
            return n
    return None


def _protection_factor(protections: str | None, expected_pick: float) -> float:
    """Convention (user-specified): a 'top-N protected' pick conveys to the
    receiving team ONLY if it lands within the top N. So a pick expected to
    land OUTSIDE the protection band rarely conveys → low value; a pick
    expected to land inside the band almost always conveys → near full value.

    `margin = threshold - expected_pick`:
      margin >> 0  → comfortably inside band, conveys (≈0.92)
      margin ≈ 0   → near boundary, coin-flip (≈0.60)
      margin << 0  → outside band, rarely conveys (floor 0.10)
    """
    if not protections:
        return 1.0
    threshold = _parse_protection_threshold(protections)
    if threshold is None:
        return 0.90
    margin = threshold - expected_pick
    factor = 0.60 + 0.05 * margin
    return max(0.10, min(0.92, factor))


def _class_strength(year: int) -> float:
    return _class_strengths().get(year, 1.0)


def pick_value(pick: DraftPick, current_year: int | None = None) -> float:
    base = _base_curve(pick.expected_pick, pick.round)
    rookie = ROOKIE_DEAL_PREMIUM if pick.round == 1 else 1.0
    return (
        base
        * rookie
        * _class_strength(pick.year)
        * _future_discount(pick.year, current_year)
        * _protection_factor(pick.protections, pick.expected_pick)
    )
