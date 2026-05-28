"""Contract surplus value as a TVS adjustment.

For each player we compute:

    expected_annual_M    = max(2.0, min(MAX_CONTRACT_M, SLOPE × tier_adjusted_tvs))
    years_factor         = sum(DISCOUNT_RATE^k for k in range(years_remaining))
    expected_total_M     = expected_annual_M × years_factor
    surplus_M            = expected_total_M - total_guaranteed_M    (positive = team-friendly)
    contract_adjustment  = surplus_M × TVS_PER_M

This means:
- Rookie-scale stars (Wemby) → big positive adjustment (years of below-market production)
- Veterans on max contracts at their level (Jokic) → near zero
- Bad multi-year overpays (Poeltl, $78M/4yr) → significant penalty
- 1-year overpay → mild penalty (expiring deal = flexibility offset)

All constants tunable; calibrated against current-season cap (~$140M, max ~$50M).
"""
from __future__ import annotations

from app.models import Player

MAX_CONTRACT_M = 50.0       # supermax ceiling in current era
MIN_SALARY_M = 2.0          # rough vet/2-way minimum
SLOPE = 0.25                # $M per TVS unit; mid-tier starters land at ~$15-25M
DISCOUNT_RATE = 0.97        # legacy alias, kept for backward import compatibility
# Contracts INFLATE rather than discount. NBA cap is projected to grow ~7%/yr
# through the new media-deal era, so $42M in year 5 is cheaper in cap % than
# today. Picks still discount (they're uncertain); contracts grow.
CONTRACT_INFLATION_RATE = 1.07
TVS_PER_M = 0.5             # how many TVS units one $M of surplus is worth

# Star-tier intercepts: the linear SLOPE under-prices what stars actually earn
# (Irving, SGA, Tatum etc. command $35M+ even though TVS × 0.25 says $18-25M).
# Adding a flat tier-based premium captures the "star tax" without inflating
# bench/role-player expectations (T4+ unchanged → bad role-player deals like
# Poeltl still rightly take their penalty).
TIER_SALARY_INTERCEPT_M: dict[int, float] = {
    1: 15.0,   # superstar / supermax era
    2: 10.0,   # All-NBA caliber
    3: 5.0,    # All-Star caliber
    4: 3.0,    # high-end starter — real starting PFs/Cs earn $12-18M, not $9M
}

# Tier-based caps: stars (T1-T3) have reputation/intangibles that soften the
# blow of bad contracts; role players (T5+) have no such cover, so a bad
# role-player contract is closer to pure dead weight.
TIER_PENALTY_CAP: dict[int, float] = {
    1: 0.15,
    2: 0.15,
    3: 0.15,
    4: 0.25,
    5: 0.40,
    6: 0.45,
    7: 0.50,
}
DEFAULT_PENALTY_CAP = 0.30
MAX_BONUS_FRACTION = 0.40

# Rookie-max proxy: young star locked up long-term. Their TVS is still
# ascending; even a "bad-on-paper" extension usually becomes a bargain by
# year 3-4 of the deal. Soften the penalty cap.
YOUNG_STAR_PENALTY_CAP = 0.08
YOUNG_STAR_AGE_MAX = 24
YOUNG_STAR_TIER_MAX = 3
YOUNG_STAR_MIN_YEARS = 4


def _expected_annual_M(tier_adjusted_tvs: float, tier: int = 5) -> float:
    base = SLOPE * tier_adjusted_tvs + TIER_SALARY_INTERCEPT_M.get(tier, 0.0)
    return min(MAX_CONTRACT_M, max(MIN_SALARY_M, base))


def _years_factor(years_remaining: int) -> float:
    """Cap-inflation-adjusted multiplier on per-year expected salary.

    Picks discount future years (uncertainty); contracts inflate (cap growth).
    For 6 years at 7%, this returns ~7.15 (vs 5.42 with the old 0.97 discount).
    """
    if years_remaining <= 0:
        return 0.0
    return sum(CONTRACT_INFLATION_RATE**k for k in range(years_remaining))


def contract_adjustment(
    player: Player, tier_adjusted_tvs: float, tier: int = 5
) -> float:
    """TVS bonus/penalty from contract surplus over remaining years.

    Bonuses (cheap contracts) scale by MPG — a 15-mpg backup on a min deal
    isn't worth as much as a 32-mpg starter on a min deal. Penalties (bad
    contracts) still apply in full because the team is stuck with the deal.

    Returns 0 if the player has no contract data.
    """
    c = player.contract
    if c.years_remaining <= 0 or c.total_guaranteed <= 0:
        return 0.0
    expected_annual = _expected_annual_M(tier_adjusted_tvs, tier=tier)
    expected_total_M = expected_annual * _years_factor(c.years_remaining)
    total_guaranteed_M = c.total_guaranteed / 1_000_000
    surplus_M = expected_total_M - total_guaranteed_M
    raw_adj = surplus_M * TVS_PER_M

    # Scale bonus by playing role — bench player surplus is less valuable in trade
    if raw_adj > 0:
        mpg = player.stats.minutes_per_game
        role_factor = max(0.35, min(mpg / 28.0, 1.0))
        raw_adj *= role_factor

    penalty_cap_pct = TIER_PENALTY_CAP.get(tier, DEFAULT_PENALTY_CAP)
    if (
        player.age <= YOUNG_STAR_AGE_MAX
        and tier <= YOUNG_STAR_TIER_MAX
        and c.years_remaining >= YOUNG_STAR_MIN_YEARS
    ):
        penalty_cap_pct = YOUNG_STAR_PENALTY_CAP
    max_penalty = tier_adjusted_tvs * penalty_cap_pct
    max_bonus = tier_adjusted_tvs * MAX_BONUS_FRACTION
    return max(-max_penalty, min(max_bonus, raw_adj))
