"""Fairness orchestrator.

Combines tier, stats_value, pick_value, and fit into a single fairness report.
Supports 2-team trades (destination implicit — the "other side") and N-team
trades for N >= 3 (each asset must specify destination_team_id).

Fairness:
  - 2-team: 100 * (1 - |a_total - b_total| / max(a_total, b_total))
  - N-team: 100 * (1 - |worst_net| / max_team_total_traded), where worst_net is
    the most negative per-team net (receiving - sending). If no team is a net
    loser, fairness = 100.
"""
from __future__ import annotations

from app.cba.limits import TIER_LABEL, mle_amount
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
    if pick.swap_type:
        verb = "Best of" if pick.swap_type == "best_of" else "Worst of"
        partners = "/".join([pick.owner_team_id, *pick.swap_partners])
        label = f"{pick.year} R{pick.round} ({verb} {partners}, proj #{int(pick.expected_pick)})"
    else:
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


def _resolve_destination(
    sender_team_id: str,
    asset: TradeAsset,
    team_ids: list[str],
) -> str:
    """Pick the destination for an asset. For 2-team trades the destination is
    implicit; for N>=3 it must be set on the asset."""
    if asset.destination_team_id:
        if asset.destination_team_id not in team_ids:
            raise ValueError(
                f"Asset destination {asset.destination_team_id} is not a participating team"
            )
        if asset.destination_team_id == sender_team_id:
            raise ValueError(f"Asset destination cannot equal sender ({sender_team_id})")
        return asset.destination_team_id
    if len(team_ids) == 2:
        return team_ids[1] if team_ids[0] == sender_team_id else team_ids[0]
    raise ValueError(
        f"3+ team trades require destination_team_id on every asset "
        f"(missing on an asset sent by {sender_team_id})"
    )


def _resolve_exceptions(
    team_id: str,
    requested_ids: list[str],
    repo: Repository,
    tier: str,
) -> tuple[int, list[str], list[str]]:
    """Resolve a side's requested exception ids into absorption capacity.

    Returns (total_absorption, applied_ids, warnings).
    Unknown ids become warnings and contribute 0 capacity. Second-apron teams
    cannot use any exceptions (warning + 0).
    """
    if not requested_ids:
        return 0, [], []
    if tier == "second_apron":
        return 0, [], [
            "Second-apron team cannot use trade exceptions or the MLE.",
        ]
    team = repo.get_team(team_id)
    if not team:
        return 0, [], [f"Unknown team {team_id} when resolving exceptions."]
    by_id: dict[str, int] = {e.id: e.amount for e in team.trade_exceptions}
    mle_id = f"{team_id}-MLE"
    mle_cap = mle_amount(tier)  # type: ignore[arg-type]
    if mle_cap > 0:
        by_id[mle_id] = mle_cap

    total = 0
    applied: list[str] = []
    warnings: list[str] = []
    for rid in requested_ids:
        if rid not in by_id:
            warnings.append(f"Exception '{rid}' is not available for {team_id}.")
            continue
        total += by_id[rid]
        applied.append(rid)
    return total, applied, warnings


def _cba_check(
    trade: Trade, repo: Repository, team_ids: list[str]
) -> tuple[bool, list[CBASideCheck]]:
    out_per_team: dict[str, tuple[int, int]] = {}
    in_per_team: dict[str, int] = {tid: 0 for tid in team_ids}
    exceptions_per_team: dict[str, list[str]] = {tid: [] for tid in team_ids}

    for side in trade.sides:
        out_salary, out_count = _player_salaries(side.sending, repo)
        out_per_team[side.team_id] = (out_salary, out_count)
        exceptions_per_team[side.team_id] = list(side.using_exceptions)
        for asset in side.sending:
            if not asset.player_id:
                continue
            player = repo.get_player(asset.player_id)
            if not player:
                continue
            dest = _resolve_destination(side.team_id, asset, team_ids)
            in_per_team[dest] = in_per_team.get(dest, 0) + player.contract.current_salary

    cba_sides: list[CBASideCheck] = []
    all_legal = True
    for tid in team_ids:
        out_salary, out_count = out_per_team.get(tid, (0, 0))
        in_salary = in_per_team.get(tid, 0)
        tier = team_tax_tier(tid, repo)
        total_team = team_total_salary(tid, repo)
        absorption, applied_ids, exc_warnings = _resolve_exceptions(
            tid, exceptions_per_team.get(tid, []), repo, tier
        )
        # Reduce the salary the matching-rule cap must cover by the absorbed amount
        residual_in = max(0, in_salary - absorption)
        check = check_side(tid, tier, out_salary, residual_in, out_count)
        effective_max_in = check.max_salary_in + absorption

        warnings = list(check.warnings) + exc_warnings
        # Project a new TPE: net salary sent out becomes future absorption capacity.
        created_tpe = max(0, out_salary - in_salary)

        cba_sides.append(
            CBASideCheck(
                team_id=check.team_id,
                tax_tier=check.tier,
                tax_tier_label=TIER_LABEL[check.tier],
                total_team_salary=total_team,
                salary_out=check.salary_out,
                salary_in=in_salary,  # report the ACTUAL incoming salary, not residual
                max_salary_in=effective_max_in,
                legal=check.legal and not exc_warnings,
                warnings=warnings,
                n_players_sent=check.n_players_sent,
                exception_absorption=absorption,
                exceptions_used=applied_ids,
                created_tpe=created_tpe,
            )
        )
        if not check.legal or exc_warnings:
            all_legal = False
    return all_legal, cba_sides


def evaluate(trade: Trade, repo: Repository) -> FairnessReport:
    if len(trade.sides) < 2:
        raise ValueError("Trade requires at least 2 sides")

    rubric = repo.get_rubric()
    teams = {s.team_id: repo.get_team(s.team_id) for s in trade.sides}
    if any(t is None for t in teams.values()):
        missing = [tid for tid, t in teams.items() if t is None]
        raise ValueError(f"Unknown team_id(s): {missing}")

    team_ids = [s.team_id for s in trade.sides]
    if len(set(team_ids)) != len(team_ids):
        raise ValueError("Each side must be a distinct team")

    sending_by_team: dict[str, list[AssetValuation]] = {tid: [] for tid in team_ids}
    receiving_by_team: dict[str, list[AssetValuation]] = {tid: [] for tid in team_ids}

    for side in trade.sides:
        for asset in side.sending:
            dest_id = _resolve_destination(side.team_id, asset, team_ids)
            dest_team = teams[dest_id]
            assert dest_team is not None
            val = _value_asset(asset, dest_team, repo, rubric)
            sending_by_team[side.team_id].append(val)
            receiving_by_team[dest_id].append(val)

    side_vals: list[SideValuation] = []
    for tid in team_ids:
        sending_total = sum(v.total_value for v in sending_by_team[tid])
        receiving_total = sum(v.total_value for v in receiving_by_team[tid])
        side_vals.append(
            SideValuation(
                team_id=tid,
                sending=sending_by_team[tid],
                receiving=receiving_by_team[tid],
                sending_total=round(sending_total, 2),
                receiving_total=round(receiving_total, 2),
                net=round(receiving_total - sending_total, 2),
            )
        )

    if len(side_vals) == 2:
        # 2-team formula preserved for backward compat (matches existing tests).
        a_total = side_vals[0].sending_total
        b_total = side_vals[1].sending_total
        larger = max(a_total, b_total, 1.0)
        gap_ratio = abs(a_total - b_total) / larger
        fairness_score = max(0.0, 100.0 * (1.0 - gap_ratio))
    else:
        # N-team: worst-loser scoring.
        nets = [sv.net for sv in side_vals]
        worst_net = min(nets)
        max_team_total = max(
            max(sv.sending_total, sv.receiving_total) for sv in side_vals
        )
        if worst_net >= 0:
            fairness_score = 100.0
        else:
            fairness_score = max(
                0.0, 100.0 * (1.0 - abs(worst_net) / max(max_team_total, 1.0))
            )

    cba_legal, cba_sides = _cba_check(trade, repo, team_ids)

    return FairnessReport(
        sides=side_vals,
        fairness_score=round(fairness_score, 1),
        verdict=_verdict(fairness_score),  # type: ignore[arg-type]
        explanation=_build_explanation(side_vals, repo),
        cba_legal=cba_legal,
        cba_sides=cba_sides,
    )
