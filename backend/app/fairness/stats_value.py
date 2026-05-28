"""NBA Trade Value (NTV) — decomposed-subscore production rating.

Adapted from the NCAA scouting dashboard's subscore architecture (Production,
Efficiency, Impact, Two-Way) rather than a single blended composite. Each
subscore caps independently so no one stat dominates.

    raw = (production × 0.35) + (efficiency × 0.25)
        + (impact × 0.25)     + (two_way × 0.15)
        + playmaking_bonus + minutes_adjustment + free_throw_bonus
        - turnover_penalty

    tvs = raw × position_multiplier × age_curve × durability
        + (tier multiplier and contract adjustment applied in engine.py)

ACCOLADE-FREE: all_star and all_nba have ZERO weight here. Pure on-court stats.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models import Player

# Subscore weights (sum = 1.00) — impact-heavy: rewards per-possession excellence
# (BPM/VORP) over raw volume. Curry's per-min impact beats Lillard's volume.
W_PRODUCTION = 0.28
W_EFFICIENCY = 0.25
W_IMPACT = 0.32
W_TWO_WAY = 0.15

# Position-specific production caps (per-game)
_POS_PROD_CAPS: dict[str, dict[str, float]] = {
    "PG": {"pts": 27.0, "reb": 6.0, "ast": 9.0, "stl": 1.8, "blk": 0.7},
    "SG": {"pts": 26.0, "reb": 6.0, "ast": 6.0, "stl": 1.6, "blk": 0.7},
    "SF": {"pts": 25.0, "reb": 8.0, "ast": 6.0, "stl": 1.6, "blk": 1.0},
    "PF": {"pts": 24.0, "reb": 10.0, "ast": 5.0, "stl": 1.4, "blk": 1.6},
    "C": {"pts": 22.0, "reb": 12.0, "ast": 4.0, "stl": 1.2, "blk": 2.2},
}

# Position multipliers — modern NBA values wings/guards over traditional centers.
# Elite centers (Jokic, Wemby) still dominate via raw stats; this just stops
# role-player bigs from inflating via blocks/rebounds.
_POS_MULT: dict[str, float] = {
    "PG": 1.04,
    "SG": 1.02,
    "SF": 1.05,
    "PF": 1.00,
    "C": 0.92,
}


@dataclass
class Subscores:
    production: float = 0.0
    efficiency: float = 0.0
    impact: float = 0.0
    two_way: float = 0.0
    playmaking_bonus: float = 0.0
    minutes_adjustment: float = 0.0
    turnover_penalty: float = 0.0
    free_throw_bonus: float = 0.0


def _age_curve(age: int) -> float:
    """Age decay. Softened at the top — shooters/playmakers age better than the curve suggests."""
    if age <= 23:
        return 0.95
    if age <= 25:
        return 1.00
    if age <= 28:
        return 1.05
    if age <= 30:
        return 1.00
    if age <= 32:
        return 0.93
    if age <= 34:
        return 0.86
    if age <= 36:
        return 0.78
    if age <= 38:
        return 0.80   # Curry/Harden at 37-38 still produce; shooting ages well
    return 0.65


def _youth_premium(age: int) -> float:
    """Trade-value bump for young players — development runway + cheap future years.

    Distinct from the production age curve (which models current output). This
    reflects that GMs pay extra for upside on a 21-year-old vs identical stats
    on a 28-year-old.
    """
    if age <= 21:
        return 1.15
    if age <= 23:
        return 1.10
    if age <= 25:
        return 1.03
    return 1.0


def _durability(games_played: int, minutes_per_game: float) -> float:
    """Total minutes — penalizes both missed games AND limited bench roles."""
    total_min = games_played * minutes_per_game
    return min(total_min / 1700.0, 1.0)


def _production_subscore(p: Player) -> float:
    """0-100 scale. Position-capped per-game contributions."""
    caps = _POS_PROD_CAPS.get(p.position, _POS_PROD_CAPS["SF"])
    s = p.stats
    pts = min(s.points / caps["pts"], 1.0) * 35
    reb = min(s.rebounds / caps["reb"], 1.0) * 20
    ast = min(s.assists / caps["ast"], 1.0) * 20
    stl = min(s.steals / caps["stl"], 1.0) * 12
    blk = min(s.blocks / caps["blk"], 1.0) * 13
    return pts + reb + ast + stl + blk


def _efficiency_subscore(p: Player) -> float:
    """0-100 scale. PER, TS%, shooting splits, plus shot-creator bonus."""
    s = p.stats
    per_score = min(s.per / 25.0, 1.0) * 30 if s.per > 0 else 0.0
    ts_score = max(0.0, min((s.ts_pct - 0.45) / 0.20, 1.0)) * 30
    fg_score = max(0.0, min((s.fg_pct - 0.40) / 0.20, 1.0)) * 15
    three_score = max(0.0, min((s.three_pct - 0.30) / 0.15, 1.0)) * 15
    # High-USG efficient scorer bonus: rewards shot creators who maintain efficiency
    creator_bonus = 0.0
    if s.usg_pct >= 25.0 and s.ts_pct >= 0.57:
        creator_bonus = 10.0
    return per_score + ts_score + fg_score + three_score + creator_bonus


def _impact_subscore(p: Player) -> float:
    """0-100 scale. BPM, VORP, OBPM — all-in-one impact metrics."""
    s = p.stats
    # BPM: -2 (replacement) to +12 (MVP-tier) → 0 to 100
    bpm_score = max(0.0, min((s.bpm + 2.0) / 14.0, 1.0)) * 55
    # VORP: 0 to 8 → 0 to 100
    vorp_score = max(0.0, min(s.vorp / 8.0, 1.0)) * 25
    # OBPM contribution (slightly favored — offense drives most NBA value)
    obpm_score = max(0.0, min((s.obpm + 1.0) / 9.0, 1.0)) * 20
    return bpm_score + vorp_score + obpm_score


def _two_way_subscore(p: Player) -> float:
    """0-100 scale. DBPM + steals + blocks + defensive rebound contribution."""
    s = p.stats
    dbpm_score = max(0.0, min((s.dbpm + 1.0) / 5.0, 1.0)) * 60
    stocks = s.steals + s.blocks
    stocks_score = min(stocks / 3.5, 1.0) * 25
    # Defensive rebounding signal — count ~70% of total rebounds as defensive (rough)
    drb_proxy = s.rebounds * 0.7
    drb_score = min(drb_proxy / 7.0, 1.0) * 15
    return dbpm_score + stocks_score + drb_score


def _playmaking_bonus(p: Player) -> float:
    s = p.stats
    if s.assists >= 6.0 and s.ast_pct >= 25.0:
        return 5.0
    if s.assists >= 4.0 and s.ast_pct >= 20.0:
        return 2.5
    return 0.0


def _minutes_adjustment(p: Player) -> float:
    """Bench players should not score like starters — sharpen the penalty."""
    mpg = p.stats.minutes_per_game
    if mpg >= 34:
        return 4.0
    if mpg >= 30:
        return 2.0
    if mpg >= 27:
        return 0.0
    if mpg >= 22:
        return -4.0
    if mpg >= 16:
        return -8.0
    return -12.0


def _turnover_penalty(p: Player) -> float:
    s = p.stats
    penalty = 0.0
    if s.turnovers > 3.0:
        penalty += (s.turnovers - 3.0) * 2.0
    if s.tov_pct > 16.0:
        penalty += (s.tov_pct - 16.0) * 0.4
    return penalty


def _free_throw_bonus(p: Player) -> float:
    s = p.stats
    if s.fta_per_game >= 5.0 and s.ft_pct >= 0.78:
        return 3.0
    return 0.0


def _subscores(p: Player) -> Subscores:
    return Subscores(
        production=_production_subscore(p),
        efficiency=_efficiency_subscore(p),
        impact=_impact_subscore(p),
        two_way=_two_way_subscore(p),
        playmaking_bonus=_playmaking_bonus(p),
        minutes_adjustment=_minutes_adjustment(p),
        turnover_penalty=_turnover_penalty(p),
        free_throw_bonus=_free_throw_bonus(p),
    )


def subscore_breakdown(p: Player) -> dict[str, float]:
    """Public-facing rounded breakdown for the API/UI."""
    s = _subscores(p)
    return {
        "production": round(s.production, 1),
        "efficiency": round(s.efficiency, 1),
        "impact": round(s.impact, 1),
        "two_way": round(s.two_way, 1),
        "playmaking_bonus": round(s.playmaking_bonus, 1),
        "minutes_adjustment": round(s.minutes_adjustment, 1),
        "turnover_penalty": round(s.turnover_penalty, 1),
        "free_throw_bonus": round(s.free_throw_bonus, 1),
    }


def _consistency_factor(player: Player) -> float:
    """Discount players whose 5-year track record lags their recent 2-year.

    Catches both one-year wonders (Avdija) and recent breakouts (Josh Hart).
    Tightened threshold (0.60) and stronger discount (0.78) to push these guys
    out of unreasonable top-10 placements.
    """
    from app.fairness.multi_year import avg_field
    r2 = avg_field(player.season_logs, "bpm", 2)
    r5 = avg_field(player.season_logs, "bpm", 5)
    if r2 <= 0.8:  # very low recent — let the rest of the model handle it
        return 1.0
    # Breakout discount (5y << 2y): recent surge unsupported by career history
    if r5 < r2 * 0.30:
        return 0.72
    if r5 < r2 * 0.60:
        return 0.82
    # Decline penalty: career was much better than recent 2yr (Lillard-style)
    if r5 > r2 * 1.40 and player.age >= 30:
        return 0.85
    return 1.0


def stats_value(player: Player) -> float:
    """Raw NTV production rating — pre-tier, pre-contract, pre-fit."""
    s = _subscores(player)
    raw = (
        s.production * W_PRODUCTION
        + s.efficiency * W_EFFICIENCY
        + s.impact * W_IMPACT
        + s.two_way * W_TWO_WAY
        + s.playmaking_bonus
        + s.minutes_adjustment
        + s.free_throw_bonus
        - s.turnover_penalty
    )
    pos_mult = _POS_MULT.get(player.position, 1.0)
    age = _age_curve(player.age)
    youth = _youth_premium(player.age)
    dur = _durability(player.stats.games_played, player.stats.minutes_per_game)
    consistency = _consistency_factor(player)
    return max(0.0, raw) * pos_mult * age * youth * dur * consistency


def value_components(player: Player) -> dict:
    """Full transparency breakdown of how a player's raw stats_value is built."""
    s = _subscores(player)
    weighted_raw = (
        s.production * W_PRODUCTION
        + s.efficiency * W_EFFICIENCY
        + s.impact * W_IMPACT
        + s.two_way * W_TWO_WAY
        + s.playmaking_bonus
        + s.minutes_adjustment
        + s.free_throw_bonus
        - s.turnover_penalty
    )
    return {
        "subscores": {
            "production": round(s.production, 1),
            "efficiency": round(s.efficiency, 1),
            "impact": round(s.impact, 1),
            "two_way": round(s.two_way, 1),
        },
        "subscore_weights": {
            "production": W_PRODUCTION,
            "efficiency": W_EFFICIENCY,
            "impact": W_IMPACT,
            "two_way": W_TWO_WAY,
        },
        "bonuses": {
            "playmaking": round(s.playmaking_bonus, 1),
            "minutes": round(s.minutes_adjustment, 1),
            "free_throw": round(s.free_throw_bonus, 1),
            "turnover_penalty": round(-s.turnover_penalty, 1),
        },
        "weighted_raw": round(weighted_raw, 1),
        "multipliers": {
            "position": round(_POS_MULT.get(player.position, 1.0), 3),
            "age_curve": round(_age_curve(player.age), 3),
            "youth_premium": round(_youth_premium(player.age), 3),
            "durability": round(
                _durability(player.stats.games_played, player.stats.minutes_per_game), 3
            ),
            "consistency": round(_consistency_factor(player), 3),
        },
        "stats_value": round(stats_value(player), 1),
    }
