"""Diagnostic: print the full contract-adjustment math for given player IDs."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.data.repository import JsonRepository
from app.fairness.contract_value import (
    _expected_annual_M,
    _years_factor,
    contract_adjustment,
)
from app.fairness.stats_value import stats_value
from app.fairness.tier import assign_tier, tier_multiplier


def main(ids: list[str]) -> None:
    repo = JsonRepository()
    rubric = repo.get_rubric()
    for pid in ids:
        p = repo.get_player(pid)
        if not p:
            print(f"{pid}: NOT FOUND")
            continue
        sv = stats_value(p)
        tier, label = assign_tier(p, rubric)
        mult = tier_multiplier(tier, rubric)
        ta = sv * p.injury_discount * mult
        exp_annual = _expected_annual_M(ta, tier=tier)
        yf = _years_factor(p.contract.years_remaining)
        exp_total = exp_annual * yf
        guar = p.contract.total_guaranteed / 1_000_000
        surplus = exp_total - guar
        adj = contract_adjustment(p, ta, tier=tier)
        print(f"\n=== {p.name} (age {p.age}, tier {tier} {label}) ===")
        print(f"  stats_value        = {sv:.1f}")
        print(f"  tier_adjusted_tvs  = {ta:.1f}")
        print(f"  current_salary     = ${p.contract.current_salary/1e6:.1f}M")
        print(f"  total_guaranteed   = ${guar:.1f}M over {p.contract.years_remaining} yrs")
        print(f"  model EXPECTS annual  = ${exp_annual:.1f}M")
        print(f"  model EXPECTS total   = ${exp_total:.1f}M (years_factor={yf:.2f})")
        print(f"  surplus (expected - actual) = ${surplus:+.1f}M")
        print(f"  contract_adjustment       = {adj:+.2f} TVS")


if __name__ == "__main__":
    main(sys.argv[1:] or ["irvinky01", "poeltja01"])
