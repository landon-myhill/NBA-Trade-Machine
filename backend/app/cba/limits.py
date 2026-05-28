"""2025-26 NBA CBA financial thresholds.

Sources: NBA.com official 2025-26 cap announcement (June 2025).
Update annually after the league announces new BRI-derived cap.
"""
from __future__ import annotations

from typing import Literal

CAP_2025_26 = 154_647_000
LUXURY_TAX_2025_26 = 187_895_000
FIRST_APRON_2025_26 = 195_945_000
SECOND_APRON_2025_26 = 207_824_000
MINIMUM_TEAM_SALARY_2025_26 = 139_182_000  # 90% of cap

# Mid-Level Exception starting-salary amounts (2025-26). Tier-gated:
#   under_cap → Room MLE
#   over_cap / luxury_tax → Non-taxpayer MLE (full)
#   first_apron → Taxpayer MLE (mini)
#   second_apron → cannot use MLE
NON_TAXPAYER_MLE_2025_26 = 12_822_000
TAXPAYER_MLE_2025_26 = 5_138_000
ROOM_MLE_2025_26 = 8_009_000


def mle_amount(tier: "TaxTier") -> int:
    """MLE starting-salary capacity available for a team in the given tier.

    Returns 0 if the team's tier disallows MLE usage (second apron).
    """
    if tier == "second_apron":
        return 0
    if tier == "first_apron":
        return TAXPAYER_MLE_2025_26
    if tier in ("luxury_tax", "over_cap"):
        return NON_TAXPAYER_MLE_2025_26
    return ROOM_MLE_2025_26  # under_cap

TaxTier = Literal["under_cap", "over_cap", "luxury_tax", "first_apron", "second_apron"]

TIER_LABEL: dict[str, str] = {
    "under_cap": "Below Cap",
    "over_cap": "Over Cap",
    "luxury_tax": "Luxury Tax",
    "first_apron": "First Apron",
    "second_apron": "Second Apron",
}


def tax_tier(total_team_salary: int) -> TaxTier:
    if total_team_salary >= SECOND_APRON_2025_26:
        return "second_apron"
    if total_team_salary >= FIRST_APRON_2025_26:
        return "first_apron"
    if total_team_salary >= LUXURY_TAX_2025_26:
        return "luxury_tax"
    if total_team_salary >= CAP_2025_26:
        return "over_cap"
    return "under_cap"
