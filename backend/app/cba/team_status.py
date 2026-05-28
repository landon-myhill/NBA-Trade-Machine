"""Compute each team's current total salary commitment and tax tier."""
from __future__ import annotations

from functools import lru_cache

from app.cba.limits import TaxTier, tax_tier
from app.data.repository import Repository


@lru_cache(maxsize=1)
def _team_payrolls(_repo_id: int) -> dict[str, int]:
    """Hash-stable identity per Repository instance."""
    # Implementation moved to module-level function; lru_cache is parameterized
    # by repository id to invalidate if the repo singleton is replaced.
    raise NotImplementedError  # placeholder; we use the function below directly


def team_total_salary(team_id: str, repo: Repository) -> int:
    return sum(
        p.contract.current_salary
        for p in repo.list_players()
        if p.team_id == team_id
    )


def team_tax_tier(team_id: str, repo: Repository) -> TaxTier:
    return tax_tier(team_total_salary(team_id, repo))
