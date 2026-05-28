"""Team-fit bonus.

Small additive nudge: positive when the receiving team needs that position and is
trying to win now; negative when the team is rebuilding and trades for an aging vet.
Kept intentionally small so it doesn't dominate the stats+tier signal.
"""
from __future__ import annotations

from app.models import Player, Team

POSITION_FIT_BONUS = 2.0
TIMELINE_AGE_PENALTY = 3.0


def fit_bonus(player: Player, receiving_team: Team) -> float:
    bonus = 0.0
    if player.position in receiving_team.needs:
        bonus += POSITION_FIT_BONUS
    if receiving_team.timeline == "rebuild" and player.age >= 32:
        bonus -= TIMELINE_AGE_PENALTY
    if receiving_team.timeline == "contender" and player.age <= 22:
        bonus -= 1.0
    return bonus
