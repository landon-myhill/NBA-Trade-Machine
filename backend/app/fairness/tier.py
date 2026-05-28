"""Rubric-driven tier engine.

Tier matching primarily uses the composite `stats_value` (multi-subscore
production rating that blends BPM/OBPM/DBPM/VORP/PER/USG/TS) rather than BPM
alone — BPM is one input of seven, so a tier shouldn't be gated purely by it.

For prime-age players (≤30) we boost the tier-matching stats_value by their
peak-recent BPM ratio (capped at 1.5x) — so a Finals-MVP-caliber 28-year-old
gets credit for ceiling even after a down season. Players past 30 use the
blended stats only, so declined veterans tier honestly.

Legacy min_epm/min_bpm/min_vorp rules still work for backwards compatibility.
"""
from __future__ import annotations

from app.models import Player, TierRubric, TierRule

PEAK_AGE_CUTOFF = 30
PEAK_BOOST_CAP = 1.50

# Star-tier (1-3) BPM ceilings only count if the player's current/blended
# stats_value is also within reach of the tier — at least 70% of the tier's
# min_stats_value. Prevents one-fluky-season role players (esp. centers with
# BPM inflation) from being mis-tiered as All-NBA/All-Star caliber.
STAR_TIER_THRESHOLD = 3
STAR_TIER_BPM_SV_FLOOR = 0.70


def _peak_recent_bpm(player: Player) -> float:
    """Best single-season BPM across stored season_logs (>= 30 games)."""
    best = player.stats.bpm
    for log in player.season_logs:
        if log.games_played < 30:
            continue
        if log.bpm > best:
            best = log.bpm
    return best


def tier_stats_value(player: Player, current_stats_value: float) -> float:
    """stats_value used for tier matching.

    Prime-age players get a peak-recent-BPM ratio boost (capped at 1.5x) so
    one bad season doesn't drop them out of their natural tier. Older players
    use the blended stats_value only.
    """
    if player.age > PEAK_AGE_CUTOFF:
        return current_stats_value
    current_bpm = max(player.stats.bpm, 0.5)  # avoid divide-by-zero for low BPM
    peak_bpm = _peak_recent_bpm(player)
    if peak_bpm <= current_bpm:
        return current_stats_value
    ratio = min(peak_bpm / current_bpm, PEAK_BOOST_CAP)
    return current_stats_value * ratio


def _peak_recent(player: Player, field: str) -> float:
    """Tier-matching ceiling for `field`.

    Past 30: use the 2-year recent average (not the 3-year blended that may
    include prime years). Catches Lillard-style decliners whose blended is
    propped up by an old peak season.

    Prime-age (≤30): use the best single recent season — gives credit for
    ceiling without inflating with one-year wonders thanks to age-gating.
    """
    current = getattr(player.stats, field, 0.0)
    if player.age > PEAK_AGE_CUTOFF:
        # Use 2-year recent average so old peaks don't inflate the tier
        from app.fairness.multi_year import avg_field
        recent_2yr = avg_field(player.season_logs, field, 2)
        if recent_2yr > 0:
            return recent_2yr
        return current
    best = current
    for log in player.season_logs:
        if log.games_played < 30:
            continue
        val = getattr(log, field, None)
        if val is not None and val > best:
            best = val
    return best


def _matches(rule: TierRule, player: Player, tsv: float, raw_sv: float) -> bool:
    """Returns True if `player` clears the rule.

    Stat thresholds (min_stats_value / min_bpm / min_epm / min_vorp) combine
    via OR — a player matches if ANY specified stat threshold is cleared.
    This lets a player tier via composite OR via individual metric ceiling.

    Age + accolade gates still combine via AND.
    """
    s = player.stats
    sv_match = (
        rule.min_stats_value is not None and tsv >= rule.min_stats_value
    )
    # Star-tier (1-3) BPM/EPM/VORP ceilings require the RAW stats_value (not
    # the peak-BPM-ratio-boosted tsv) to also clear a floor. Blocks one-season-
    # wonder role players (Gafford 2024-25 BPM 3.8 fluke) from being mis-tiered
    # as All-NBA/All-Star caliber. The boosted tsv already lets *stars in a
    # down year* qualify via min_stats_value path.
    is_star_tier = rule.tier <= STAR_TIER_THRESHOLD
    sv_floor_met = True
    if is_star_tier and rule.min_stats_value is not None:
        sv_floor_met = raw_sv >= rule.min_stats_value * STAR_TIER_BPM_SV_FLOOR

    stat_conds: list[bool] = []
    if rule.min_stats_value is not None:
        stat_conds.append(sv_match)
    if rule.min_epm is not None:
        peak_epm = max(s.epm, _peak_recent(player, "bpm"))
        stat_conds.append(peak_epm >= rule.min_epm and sv_floor_met)
    if rule.min_bpm is not None:
        stat_conds.append(_peak_recent(player, "bpm") >= rule.min_bpm and sv_floor_met)
    if rule.min_vorp is not None:
        stat_conds.append(_peak_recent(player, "vorp") >= rule.min_vorp and sv_floor_met)
    if stat_conds and not any(stat_conds):
        return False
    if rule.min_age is not None and player.age < rule.min_age:
        return False
    if rule.max_age is not None and player.age > rule.max_age:
        return False
    if rule.requires_all_nba and not s.all_nba:
        return False
    if rule.requires_all_star and not s.all_star:
        return False
    return True


def assign_tier(player: Player, rubric: TierRubric) -> tuple[int, str]:
    """Returns (tier_number, tier_label) for the first matching rule."""
    from app.fairness.stats_value import stats_value
    raw_sv = stats_value(player)
    tsv = tier_stats_value(player, raw_sv)
    for rule in sorted(rubric.rules, key=lambda r: r.tier):
        if _matches(rule, player, tsv, raw_sv):
            return rule.tier, rule.label
    return rubric.default_tier, "Unranked"


def tier_multiplier(tier: int, rubric: TierRubric) -> float:
    return rubric.multipliers.get(tier, rubric.multipliers.get(str(tier), 1.0))  # type: ignore[arg-type]
