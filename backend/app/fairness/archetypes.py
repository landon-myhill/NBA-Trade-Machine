"""Player archetype classification.

Pure post-hoc labels — does NOT affect TVS rating. Provides a quick read on what
kind of player you're trading for (Floor General, 3&D Wing, Stretch 5, etc.).

Adapted from the NCAA scouting dashboard archetype system, simplified for the NBA
where we don't have college-specific signals.
"""
from __future__ import annotations

from app.models import Player

# Thresholds tuned against the 2025-26 league distribution.

# --- Guards ---
def _is_elite_floor_general(p: Player) -> bool:
    s = p.stats
    return (
        s.assists >= 7.0
        and s.ast_pct >= 28.0
        and s.points >= 18.0
        and s.ts_pct >= 0.55
    )


def _is_floor_general(p: Player) -> bool:
    s = p.stats
    return s.assists >= 5.5 and s.ast_pct >= 22.0


def _is_scoring_guard(p: Player) -> bool:
    s = p.stats
    return (
        p.position in ("PG", "SG")
        and s.points >= 18.0
        and s.usg_pct >= 25.0
    )


def _is_three_and_d_guard(p: Player) -> bool:
    s = p.stats
    return (
        p.position in ("PG", "SG")
        and s.three_attempts_per_game >= 4.0
        and s.three_pct >= 0.36
        and s.dbpm >= 0.5
    )


def _is_combo_guard(p: Player) -> bool:
    s = p.stats
    return (
        p.position in ("PG", "SG")
        and s.points >= 14.0
        and s.assists >= 3.5
    )


# --- Wings/Forwards ---
def _is_three_level_scorer(p: Player) -> bool:
    s = p.stats
    return (
        p.position in ("SG", "SF", "PF")
        and s.points >= 22.0
        and s.three_pct >= 0.34
        and s.ft_pct >= 0.75
        and s.fta_per_game >= 4.0
    )


def _is_two_way_wing(p: Player) -> bool:
    s = p.stats
    return (
        p.position in ("SG", "SF", "PF")
        and s.dbpm >= 1.5
        and s.points >= 12.0
        and (s.steals + s.blocks) >= 1.5
    )


def _is_sharpshooter(p: Player) -> bool:
    s = p.stats
    return (
        s.three_attempts_per_game >= 5.0
        and s.three_pct >= 0.38
    )


def _is_point_forward(p: Player) -> bool:
    s = p.stats
    return (
        p.position in ("SF", "PF")
        and s.assists >= 5.0
        and s.rebounds >= 5.0
    )


# --- Bigs ---
def _is_stretch_five(p: Player) -> bool:
    s = p.stats
    return (
        p.position == "C"
        and s.three_attempts_per_game >= 2.5
        and s.three_pct >= 0.34
    )


def _is_modern_big(p: Player) -> bool:
    s = p.stats
    return (
        p.position in ("PF", "C")
        and s.assists >= 3.5
        and s.blocks >= 1.0
    )


def _is_glass_cleaner(p: Player) -> bool:
    s = p.stats
    return (
        p.position in ("PF", "C")
        and s.rebounds >= 10.0
    )


def _is_paint_anchor(p: Player) -> bool:
    s = p.stats
    return (
        p.position == "C"
        and s.blocks >= 1.5
        and s.dbpm >= 1.5
    )


def _is_post_scorer(p: Player) -> bool:
    s = p.stats
    return (
        p.position in ("PF", "C")
        and s.points >= 17.0
        and s.usg_pct >= 24.0
        and s.three_attempts_per_game < 3.0
    )


# Generic fallbacks
def _is_volume_scorer(p: Player) -> bool:
    return p.stats.points >= 18.0 and p.stats.usg_pct >= 25.0


def _is_rim_protector(p: Player) -> bool:
    return p.stats.blocks >= 1.3


def _is_rebounder(p: Player) -> bool:
    return p.stats.rebounds >= 8.0


def _is_low_minutes(p: Player) -> bool:
    return p.stats.minutes_per_game < 15.0


def classify(player: Player) -> str:
    """Return the player's primary archetype. First match wins."""
    if _is_low_minutes(player):
        return "Deep Bench"
    # Guards (most specific first)
    if _is_elite_floor_general(player):
        return "Elite Floor General"
    if _is_three_and_d_guard(player):
        return "3&D Guard"
    if _is_floor_general(player):
        return "Floor General"
    if _is_scoring_guard(player):
        return "Scoring Guard"
    # Wings
    if _is_three_level_scorer(player):
        return "Three-Level Scorer"
    if _is_two_way_wing(player):
        return "Two-Way Wing"
    if _is_point_forward(player):
        return "Point Forward"
    if _is_sharpshooter(player):
        return "Sharpshooter"
    # Bigs
    if _is_stretch_five(player):
        return "Stretch 5"
    if _is_paint_anchor(player):
        return "Paint Anchor"
    if _is_modern_big(player):
        return "Modern Big"
    if _is_post_scorer(player):
        return "Post Scorer"
    if _is_glass_cleaner(player):
        return "Glass Cleaner"
    # Guards last-ditch
    if _is_combo_guard(player):
        return "Combo Guard"
    # Generic fallbacks
    if _is_volume_scorer(player):
        return "Volume Scorer"
    if _is_rim_protector(player):
        return "Rim Protector"
    if _is_rebounder(player):
        return "Rebounder"
    return "Role Player"
