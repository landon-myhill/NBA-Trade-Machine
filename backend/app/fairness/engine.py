"""Fairness orchestrator.

Combines tier, stats_value, pick_value, and fit into a single fairness report.
v1 supports 2-team trades. 3+ team trades require explicit per-asset destinations
and are rejected with HTTP 400 by the route layer.
"""
from __future__ import annotations

from app.cba.limits import TIER_LABEL
from app.cba.matching import check_side
from app.cba.team_status import team_tax_tier, team_total_salary
from app.data.repository import Repository
from app.fairness.contract_value import contract_adjustment
from app.fairness.fit import fit_bonus
from app.fairness.pick_value import pick_value
from app.fairness.stats_value import stats_value, subscore_breakdown
from app.fairness.tier import assign_tier, tier_multiplier
from app.models import (
    AssetValuation,
    CBASideCheck,
    DraftPick,
    FairnessReport,
    Player,
    SideValuation,
    SubscoreBreakdown,
    Team,
    TierRubric,
    Trade,
    TradeAsset,
)

LOPSIDED_THRESHOLDS = (0.10, 0.25, 0.50)  # fair / slightly_uneven / lopsided / very_lopsided


def _value_player(
    player: Player, receiving_team: Team, rubric: TierRubric
) -> AssetValuation:
    sv = stats_value(player)
    sub = subscore_breakdown(player)
    tier, label = assign_tier(player, rubric)
    mult = tier_multiplier(tier, rubric)
    # Apply injury discount BEFORE tier multiplier so it scales with raw production
    health_adjusted = sv * player.injury_discount
    tier_adjusted = health_adjusted * mult
    contract_adj = contract_adjustment(player, tier_adjusted, tier=tier)
    bonus = fit_bonus(player, receiving_team)
    total = tier_adjusted + contract_adj + bonus
    return AssetValuation(
        label=player.name,
        kind="player",
        stats_value=round(sv, 2),
        subscores=SubscoreBreakdown(**sub),
        archetype=player.archetype,
        tier=tier,
        tier_label=label,
        tier_multiplier=mult,
        contract_adjustment=round(contract_adj, 2),
        current_salary=player.contract.current_salary,
        fit_bonus=round(bonus, 2),
        total_value=round(total, 2),
    )


def _value_pick(pick: DraftPick) -> AssetValuation:
    pv = pick_value(pick)
    label = f"{pick.year} R{pick.round} (exp. #{int(pick.expected_pick)}"
    if pick.origin_team_id != pick.owner_team_id:
        label += f", via {pick.origin_team_id}"
    label += ")"
    if pick.protections:
        label += f" [{pick.protections}]"
    return AssetValuation(
        label=label,
        kind="pick",
        stats_value=round(pv, 2),
        tier=None,
        tier_label=None,
        tier_multiplier=1.0,
        fit_bonus=0.0,
        total_value=round(pv, 2),
    )


def _value_asset(
    asset: TradeAsset, receiving_team: Team, repo: Repository, rubric: TierRubric
) -> AssetValuation:
    if asset.player_id:
        player = repo.get_player(asset.player_id)
        if not player:
            raise ValueError(f"Unknown player_id: {asset.player_id}")
        return _value_player(player, receiving_team, rubric)
    if asset.pick_id:
        pick = repo.get_pick(asset.pick_id)
        if not pick:
            raise ValueError(f"Unknown pick_id: {asset.pick_id}")
        return _value_pick(pick)
    raise ValueError("TradeAsset must have either player_id or pick_id")


def _verdict(fairness_score: float) -> str:
    if fairness_score >= 90:
        return "fair"
    if fairness_score >= 75:
        return "slightly_uneven"
    if fairness_score >= 50:
        return "lopsided"
    return "very_lopsided"


def _build_explanation(side_vals: list[SideValuation], repo: Repository) -> list[str]:
    lines: list[str] = []
    teams_by_id = {t.id: t for t in repo.list_teams()}
    for sv in side_vals:
        team = teams_by_id.get(sv.team_id)
        team_name = team.name if team else sv.team_id
        direction = "gains" if sv.net >= 0 else "loses"
        lines.append(
            f"{team_name} {direction} {abs(sv.net):.1f} value "
            f"(send {sv.sending_total:.1f}, receive {sv.receiving_total:.1f})."
        )
    return lines


def _player_salaries(assets: list[TradeAsset], repo: Repository) -> tuple[int, int]:
    """Returns (total_player_salary, n_players). Picks contribute $0 and don't count."""
    total = 0
    count = 0
    for a in assets:
        if a.player_id:
            player = repo.get_player(a.player_id)
            if player:
                total += player.contract.current_salary
                count += 1
    return total, count


def _cba_check(trade: Trade, repo: Repository) -> tuple[bool, list[CBASideCheck]]:
    side_a, side_b = trade.sides[0], trade.sides[1]
    a_out, a_n = _player_salaries(side_a.sending, repo)
    b_out, b_n = _player_salaries(side_b.sending, repo)

    tier_a = team_tax_tier(side_a.team_id, repo)
    tier_b = team_tax_tier(side_b.team_id, repo)
    total_a = team_total_salary(side_a.team_id, repo)
    total_b = team_total_salary(side_b.team_id, repo)

    check_a = check_side(side_a.team_id, tier_a, a_out, b_out, a_n)
    check_b = check_side(side_b.team_id, tier_b, b_out, a_out, b_n)

    cba_sides = [
        CBASideCheck(
            team_id=check_a.team_id,
            tax_tier=check_a.tier,
            tax_tier_label=TIER_LABEL[check_a.tier],
            total_team_salary=total_a,
            salary_out=check_a.salary_out,
            salary_in=check_a.salary_in,
            max_salary_in=check_a.max_salary_in,
            legal=check_a.legal,
            warnings=check_a.warnings,
            n_players_sent=check_a.n_players_sent,
        ),
        CBASideCheck(
            team_id=check_b.team_id,
            tax_tier=check_b.tier,
            tax_tier_label=TIER_LABEL[check_b.tier],
            total_team_salary=total_b,
            salary_out=check_b.salary_out,
            salary_in=check_b.salary_in,
            max_salary_in=check_b.max_salary_in,
            legal=check_b.legal,
            warnings=check_b.warnings,
            n_players_sent=check_b.n_players_sent,
        ),
    ]
    return (check_a.legal and check_b.legal), cba_sides


def evaluate(trade: Trade, repo: Repository) -> FairnessReport:
    if len(trade.sides) != 2:
        raise ValueError("v1 only supports 2-team trades")

    rubric = repo.get_rubric()
    teams = {s.team_id: repo.get_team(s.team_id) for s in trade.sides}
    if any(t is None for t in teams.values()):
        missing = [tid for tid, t in teams.items() if t is None]
        raise ValueError(f"Unknown team_id(s): {missing}")

    side_a, side_b = trade.sides[0], trade.sides[1]
    team_a, team_b = teams[side_a.team_id], teams[side_b.team_id]
    assert team_a is not None and team_b is not None

    a_sending = [_value_asset(a, team_b, repo, rubric) for a in side_a.sending]
    b_sending = [_value_asset(a, team_a, repo, rubric) for a in side_b.sending]

    a_sending_total = sum(v.total_value for v in a_sending)
    b_sending_total = sum(v.total_value for v in b_sending)

    side_a_val = SideValuation(
        team_id=side_a.team_id,
        sending=a_sending,
        receiving=b_sending,
        sending_total=round(a_sending_total, 2),
        receiving_total=round(b_sending_total, 2),
        net=round(b_sending_total - a_sending_total, 2),
    )
    side_b_val = SideValuation(
        team_id=side_b.team_id,
        sending=b_sending,
        receiving=a_sending,
        sending_total=round(b_sending_total, 2),
        receiving_total=round(a_sending_total, 2),
        net=round(a_sending_total - b_sending_total, 2),
    )

    larger = max(a_sending_total, b_sending_total, 1.0)
    gap_ratio = abs(a_sending_total - b_sending_total) / larger
    fairness_score = max(0.0, 100.0 * (1.0 - gap_ratio))

    cba_legal, cba_sides = _cba_check(trade, repo)

    return FairnessReport(
        sides=[side_a_val, side_b_val],
        fairness_score=round(fairness_score, 1),
        verdict=_verdict(fairness_score),  # type: ignore[arg-type]
        explanation=_build_explanation([side_a_val, side_b_val], repo),
        cba_legal=cba_legal,
        cba_sides=cba_sides,
    )
