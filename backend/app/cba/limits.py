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
