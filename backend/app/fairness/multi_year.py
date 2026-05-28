"""Multi-year stats blending.

Takes a player's season logs (newest-first) and produces an "effective" stat
profile representing their typical production — useful for hurt players whose
current-year stats don't reflect their real ability.

    weights: 0.55 / 0.30 / 0.15 (most recent → 3 years ago)
    filter:  seasons with games_played >= 10 (skip token appearances)

Also computes an injury discount based on most-recent-season games played:
    games >= 50  → 1.00 (no discount)
    games == 25  → 0.83
    games == 0   → 0.65 (cap)
"""
from __future__ import annotations

from typing import Any

# Stats that get blended numerically (per-game, percentages, advanced)
_BLENDED_FIELDS = (
    "minutes_per_game", "points", "rebounds", "assists",
    "steals", "blocks", "turnovers",
    "fg_pct", "three_pct", "ft_pct", "fta_per_game", "three_attempts_per_game",
    "bpm", "obpm", "dbpm", "vorp", "per",
    "usg_pct", "ts_pct", "ast_pct", "tov_pct",
)

# How seasons before the current (most-recent) one are weighted
_DECAY_WEIGHTS = [0.55, 0.30, 0.15]

INJURY_MIN_DISCOUNT = 0.88  # missed full season: 12% hit — most NBA injuries recover within a season
INJURY_FULL_GAMES = 50  # at this many games or more, no discount


def _valid_logs(logs: list[dict[str, Any]], min_games: int = 10) -> list[dict[str, Any]]:
    return [l for l in logs if l.get("games_played", 0) >= min_games]


def effective_stats(logs: list[dict[str, Any]]) -> dict[str, Any]:
    """Returns blended stats dict suitable for PlayerStats(**result)."""
    valid = _valid_logs(logs)[:3]
    if not valid:
        valid = logs[:3] if logs else [{}]

    # Normalize weights to sum to 1.0
    weights = _DECAY_WEIGHTS[: len(valid)]
    total_w = sum(weights) or 1.0
    weights = [w / total_w for w in weights]

    blended: dict[str, Any] = {}
    for field in _BLENDED_FIELDS:
        blended[field] = sum(
            float(log.get(field, 0) or 0) * w for log, w in zip(valid, weights)
        )
    # games_played: use blended (represents typical "healthy" durability)
    blended["games_played"] = int(
        sum(int(log.get("games_played", 0) or 0) * w for log, w in zip(valid, weights))
    )
    # Season label: most recent contributing season
    blended["season"] = valid[0].get("season", "")
    # Awards: take the OR across the blended seasons (was the player an All-Star in any?)
    blended["all_star"] = any(log.get("all_star") for log in valid)
    blended["all_nba"] = any(log.get("all_nba") for log in valid)
    # Defaults required by PlayerStats schema but not blended
    blended.setdefault("efg_pct", 0.0)
    return blended


def latest_played_season(logs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Most recent season the player actually played in (games_played > 0)."""
    for log in logs:
        if log.get("games_played", 0) > 0:
            return log
    return logs[0] if logs else None


def injury_discount(logs: list[dict[str, Any]], current_season: str) -> float:
    """Returns multiplier in [INJURY_MIN_DISCOUNT, 1.0] based on most-recent games played.

    If the player's latest log IS the current season, that season's GP drives the discount.
    If the player has no current-season log (totally missed), discount uses games=0.
    """
    current_log = next((l for l in logs if l.get("season") == current_season), None)
    games = current_log.get("games_played", 0) if current_log else 0
    ratio = min(games / INJURY_FULL_GAMES, 1.0)
    return INJURY_MIN_DISCOUNT + (1.0 - INJURY_MIN_DISCOUNT) * ratio


def avg_field(logs: list, field: str, n: int, min_games: int = 30) -> float:
    """Simple average of `field` across last `n` valid season logs.

    Accepts either dict-shaped raw history rows or SeasonLog Pydantic models —
    uses .get for dicts, getattr for objects.
    """
    valid = []
    for log in logs:
        gp = log.get("games_played", 0) if isinstance(log, dict) else getattr(log, "games_played", 0)
        if gp >= min_games:
            valid.append(log)
        if len(valid) >= n:
            break
    if not valid:
        return 0.0
    total = 0.0
    for log in valid:
        v = log.get(field, 0) if isinstance(log, dict) else getattr(log, field, 0)
        total += float(v or 0)
    return total / len(valid)


def trend_ratio(logs: list, field: str = "bpm") -> float:
    """recent_2yr_avg / career_5yr_avg — > 1.0 = improving, < 1.0 = declining."""
    recent = avg_field(logs, field, 2)
    career = avg_field(logs, field, 5)
    if career == 0:
        return 1.0
    return recent / career


def season_log_for_player(log: dict[str, Any]) -> dict[str, Any]:
    """Project a raw history dict down to the SeasonLog schema."""
    return {
        "season": log.get("season", ""),
        "games_played": int(log.get("games_played", 0) or 0),
        "minutes_per_game": float(log.get("minutes_per_game", 0) or 0),
        "points": float(log.get("points", 0) or 0),
        "rebounds": float(log.get("rebounds", 0) or 0),
        "assists": float(log.get("assists", 0) or 0),
        "bpm": float(log.get("bpm", 0) or 0),
        "vorp": float(log.get("vorp", 0) or 0),
        "ts_pct": float(log.get("ts_pct", 0) or 0),
        "usg_pct": float(log.get("usg_pct", 0) or 0),
    }
