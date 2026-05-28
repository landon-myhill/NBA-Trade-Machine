"""2023 CBA salary-matching rules for trades.

Three tier-driven matching tables:

  Non-taxpayer (below luxury tax):
      outgoing ≤ $7.5M   → max incoming = 200% of outgoing + $250,000
      outgoing ≤ $30M    → max incoming = 175% of outgoing
      outgoing >  $30M   → max incoming = 125% of outgoing + $250,000

  Taxpayer (luxury tax through first apron):
      max incoming = 110% of outgoing + $100,000

  Second-apron taxpayer:
      max incoming = 100% of outgoing                (dollar-for-dollar)
      + cannot aggregate salaries (each outgoing player must individually match)
      + cannot send out cash
      + cannot use TPE > $7.5M

Returns structured results so the engine can surface specific violations
rather than just "illegal".
"""
from __future__ import annotations

from dataclasses import dataclass

from app.cba.limits import TaxTier

NON_TAX_TIER1_BREAKPOINT = 7_500_000
NON_TAX_TIER2_BREAKPOINT = 30_000_000


def max_incoming_salary(outgoing: int, tier: TaxTier) -> int:
    """Largest legal incoming salary given outgoing dollars + sender's tax tier."""
    if tier == "second_apron":
        return outgoing
    if tier in ("first_apron", "luxury_tax"):
        return int(outgoing * 1.10 + 100_000)
    # Below tax — graduated brackets
    if outgoing <= NON_TAX_TIER1_BREAKPOINT:
        return int(outgoing * 2.0 + 250_000)
    if outgoing <= NON_TAX_TIER2_BREAKPOINT:
        return int(outgoing * 1.75)
    return int(outgoing * 1.25 + 250_000)


@dataclass
class SideCheck:
    team_id: str
    tier: TaxTier
    salary_out: int
    salary_in: int
    max_salary_in: int
    legal: bool
    warnings: list[str]
    n_players_sent: int


def check_side(
    team_id: str,
    tier: TaxTier,
    salary_out: int,
    salary_in: int,
    n_players_sent: int,
) -> SideCheck:
    """Validate one side of a trade against its sender's apron tier."""
    max_in = max_incoming_salary(salary_out, tier)
    legal = salary_in <= max_in
    warnings: list[str] = []

    if tier == "second_apron" and n_players_sent > 1:
        warnings.append(
            "Second-apron team cannot aggregate salaries — each outgoing player "
            "must individually match an incoming player's salary."
        )
        legal = False  # aggregation is hard-illegal at second apron

    if not legal and salary_in > max_in:
        excess = salary_in - max_in
        warnings.append(
            f"Incoming salary ${salary_in:,} exceeds the ${max_in:,} cap by "
            f"${excess:,} (sender is {tier.replace('_', ' ')})."
        )

    return SideCheck(
        team_id=team_id,
        tier=tier,
        salary_out=salary_out,
        salary_in=salary_in,
        max_salary_in=max_in,
        legal=legal,
        warnings=warnings,
        n_players_sent=n_players_sent,
    )
