"""Trade finder — given a target player and an acquiring team, suggest packages
that are both fair (within a TVS gap threshold) and CBA-legal.

Enumerates combinations of the acquiring team's players (+ optional picks) up to
`max_players` assets, scores each, and returns the best matches.
"""
from __future__ import annotations

from itertools import combinations

from app.cba.limits import TIER_LABEL, mle_amount
from app.cba.matching import max_incoming_salary
from app.cba.team_status import team_tax_tier
from app.data.repository import Repository
from app.fairness.contract_value import contract_adjustment
from app.fairness.pick_value import pick_value
from app.fairness.stats_value import stats_value
from app.fairness.tier import assign_tier, tier_multiplier
from app.models import Player

FAIR_GAP = 0.15  # package within 15% of target value counts as fair

# Return-preference thresholds for the league-wide finder filter chips.
STAR_TIER_MAX = 3  # tier 1 (Superstar) through tier 3 (All-Star caliber)
YOUNG_AGE_MAX = 25  # 25 and under counts as "young assets"
VALID_RETURN_PREFERENCES = frozenset({"star", "young", "picks"})


def _player_tvs(player: Player, rubric) -> float:
    sv = stats_value(player)
    tier, _ = assign_tier(player, rubric)
    mult = tier_multiplier(tier, rubric)
    tier_adj = sv * player.injury_discount * mult
    return tier_adj + contract_adjustment(player, tier_adj, tier=tier)


def find_packages(
    target_player_id: str,
    acquiring_team_id: str,
    repo: Repository,
    max_players: int = 3,
    max_picks: int = 2,
    include_picks: bool = True,
    limit: int = 15,
) -> dict:
    rubric = repo.get_rubric()
    target = repo.get_player(target_player_id)
    if not target:
        raise ValueError(f"Unknown target player: {target_player_id}")
    if not repo.get_team(acquiring_team_id):
        raise ValueError(f"Unknown team: {acquiring_team_id}")

    target_tvs = _player_tvs(target, rubric)
    target_salary = target.contract.current_salary
    seller_team = target.team_id

    # Acquiring team's tradeable assets
    players = [p for p in repo.list_players() if p.team_id == acquiring_team_id]
    picks = (
        [pk for pk in repo.list_picks() if pk.owner_team_id == acquiring_team_id]
        if include_picks
        else []
    )

    player_tvs = {p.id: _player_tvs(p, rubric) for p in players}
    pick_tvs = {pk.id: pick_value(pk) for pk in picks}

    acquirer_tier = team_tax_tier(acquiring_team_id, repo)

    # Pre-enumerate pick combos (0..max_picks) with their summed value
    pick_combos: list[tuple[tuple, float]] = [((), 0.0)]
    for k in range(1, max_picks + 1):
        for pcombo in combinations(picks, k):
            pick_combos.append((pcombo, sum(pick_tvs[pk.id] for pk in pcombo)))

    results = []
    # Player combos of size 0..max_players × pick combos; skip the empty package
    for n in range(0, max_players + 1):
        for combo in combinations(players, n):
            base_tvs = sum(player_tvs[p.id] for p in combo)
            salary_out = sum(p.contract.current_salary for p in combo)
            for pcombo, pcombo_tvs in pick_combos:
                if not combo and not pcombo:
                    continue
                total_tvs = base_tvs + pcombo_tvs
                gap = abs(total_tvs - target_tvs) / max(target_tvs, 1.0)
                if gap > FAIR_GAP:
                    continue
                max_in = max_incoming_salary(salary_out, acquirer_tier)
                legal = target_salary <= max_in
                if acquirer_tier == "second_apron" and len(combo) > 1:
                    legal = False
                # Pick-only or pick-heavy deals still need salary to match if a
                # player is incoming — picks carry $0, so salary_out must cover it.
                assets = [
                    {"kind": "player", "id": p.id, "name": p.name, "tvs": round(player_tvs[p.id], 1)}
                    for p in combo
                ]
                for pk in pcombo:
                    assets.append(_asset_dict_pick(pk, pick_tvs[pk.id]))
                results.append(
                    {
                        "assets": assets,
                        "package_tvs": round(total_tvs, 1),
                        "gap_pct": round(gap * 100, 1),
                        "salary_out": salary_out,
                        "salary_in": target_salary,
                        "max_salary_in": max_in,
                        "cba_legal": legal,
                        "n_assets": len(assets),
                    }
                )

    # Prefer legal, then FEWEST assets (cleaner deals), then closest gap.
    # Fewest-first stops 3-player fine-tuned packages from dominating the list.
    results.sort(key=lambda r: (not r["cba_legal"], r["n_assets"], r["gap_pct"]))
    return {
        "target": {
            "id": target.id,
            "name": target.name,
            "team_id": seller_team,
            "tvs": round(target_tvs, 1),
            "salary": target_salary,
        },
        "acquiring_team_id": acquiring_team_id,
        "acquirer_tax_tier": acquirer_tier,
        "acquirer_tax_tier_label": TIER_LABEL[acquirer_tier],
        "packages": results[:limit],
    }


def _resolve_anchors(
    anchors: list[dict], team_id: str, repo: Repository
) -> tuple[list[Player], list]:
    """Split anchor refs into Players/Picks and validate they belong to the team."""
    players: list[Player] = []
    picks: list = []
    for ref in anchors:
        pid = ref.get("player_id")
        ckid = ref.get("pick_id")
        if pid:
            p = repo.get_player(pid)
            if not p:
                raise ValueError(f"Unknown player_id: {pid}")
            if p.team_id != team_id:
                raise ValueError(f"Player {p.name} is not on team {team_id}")
            players.append(p)
        elif ckid:
            pk = repo.get_pick(ckid)
            if not pk:
                raise ValueError(f"Unknown pick_id: {ckid}")
            if pk.owner_team_id != team_id:
                raise ValueError(f"Pick {pk.id} is not owned by {team_id}")
            picks.append(pk)
        else:
            raise ValueError("Anchor must have player_id or pick_id")
    return players, picks


def _asset_dict_player(p: Player, tvs: float) -> dict:
    return {"kind": "player", "id": p.id, "name": p.name, "tvs": round(tvs, 1)}


def _asset_dict_pick(pk, tvs: float) -> dict:
    if pk.swap_type:
        verb = "Best of" if pk.swap_type == "best_of" else "Worst of"
        partners = "/".join([pk.owner_team_id, *pk.swap_partners])
        name = f"{pk.year} R{pk.round} ({verb} {partners}, proj #{int(pk.expected_pick)})"
    else:
        name = f"{pk.year} R{pk.round} (#{int(pk.expected_pick)})"
        if pk.origin_team_id != pk.owner_team_id:
            name += f" via {pk.origin_team_id}"
    if pk.protections:
        name += f" [{pk.protections}]"
    return {"kind": "pick", "id": pk.id, "name": name, "tvs": round(tvs, 1)}


def _suggestion_matches_preferences(
    suggestion: dict,
    preferences: list[str],
    repo: Repository,
    rubric,
    picks_min_count: int = 1,
    picks_years: list[int] | None = None,
    picks_round: int | None = None,
) -> bool:
    """OR-semantics: keep if at least one addition matches at least one preference.

    The 'picks' preference is refined by picks_min_count / picks_years /
    picks_round — the package must contain at least picks_min_count picks
    that match the year and round filters (empty lists / None = any).
    """
    if not preferences:
        return True
    # Star and Young can short-circuit early — they're per-player checks.
    for asset in suggestion["additions"]:
        if asset["kind"] != "player":
            continue
        player = repo.get_player(asset["id"])
        if not player:
            continue
        if "young" in preferences and player.age <= YOUNG_AGE_MAX:
            return True
        if "star" in preferences:
            tier, _ = assign_tier(player, rubric)
            if tier <= STAR_TIER_MAX:
                return True

    # Picks: count picks matching year + round filters; require >= picks_min_count.
    if "picks" in preferences:
        matching = 0
        for asset in suggestion["additions"]:
            if asset["kind"] != "pick":
                continue
            pick = repo.get_pick(asset["id"])
            if not pick:
                continue
            if picks_years and pick.year not in picks_years:
                continue
            if picks_round is not None and pick.round != picks_round:
                continue
            matching += 1
        if matching >= picks_min_count:
            return True
    return False


def find_balancing_additions(
    team_a_id: str,
    team_b_id: str | None,
    anchors_a: list[dict],
    anchors_b: list[dict],
    repo: Repository,
    max_additions: int = 2,
    limit: int = 10,
    return_preferences: list[str] | None = None,
    picks_min_count: int = 1,
    picks_years: list[int] | None = None,
    picks_round: int | None = None,
    excluded_player_ids: list[str] | None = None,
    fair_gap_threshold: float = FAIR_GAP,
) -> dict:
    """Two-sided anchored finder.

    Given pieces locked on each side, evaluate the deal as-anchored, then search
    the lighter-value side's remaining roster for the smallest set of additions
    that (a) brings the gap within FAIR_GAP and (b) passes CBA.

    Modes:
      - team_b_id specified: search only Side B's roster for additions.
      - team_b_id is None  : "league-wide" search. Side A pins assets, then the
        finder runs the single-team search against EVERY other team and merges
        results, ranked by (legal, fewest additions, gap). anchors_b must be
        empty in this mode (no other team to pin assets on).
    """
    if team_b_id is None:
        return _find_balancing_across_league(
            team_a_id,
            anchors_a,
            anchors_b,
            repo,
            max_additions,
            limit,
            return_preferences or [],
            picks_min_count,
            picks_years or [],
            picks_round,
            excluded_player_ids or [],
            fair_gap_threshold,
        )

    rubric = repo.get_rubric()
    team_a = repo.get_team(team_a_id)
    team_b = repo.get_team(team_b_id)
    if not team_a or not team_b:
        raise ValueError("Unknown team_id")
    if team_a_id == team_b_id:
        raise ValueError("Both sides must be different teams")

    anchor_a_players, anchor_a_picks = _resolve_anchors(anchors_a, team_a_id, repo)
    anchor_b_players, anchor_b_picks = _resolve_anchors(anchors_b, team_b_id, repo)
    if not (anchor_a_players or anchor_a_picks) and not (anchor_b_players or anchor_b_picks):
        raise ValueError("At least one side must have an anchored asset")

    # Per-asset TVS lookup (anchors + every potential addition)
    anchor_player_tvs = {p.id: _player_tvs(p, rubric) for p in anchor_a_players + anchor_b_players}
    anchor_pick_tvs = {pk.id: pick_value(pk) for pk in anchor_a_picks + anchor_b_picks}

    anchored_a_tvs = sum(anchor_player_tvs[p.id] for p in anchor_a_players) + sum(
        anchor_pick_tvs[pk.id] for pk in anchor_a_picks
    )
    anchored_b_tvs = sum(anchor_player_tvs[p.id] for p in anchor_b_players) + sum(
        anchor_pick_tvs[pk.id] for pk in anchor_b_picks
    )
    anchored_a_salary = sum(p.contract.current_salary for p in anchor_a_players)
    anchored_b_salary = sum(p.contract.current_salary for p in anchor_b_players)

    tier_a = team_tax_tier(team_a_id, repo)
    tier_b = team_tax_tier(team_b_id, repo)

    def score(a_tvs: float, b_tvs: float) -> tuple[float, float]:
        larger = max(a_tvs, b_tvs, 1.0)
        gap = abs(a_tvs - b_tvs) / larger
        fairness = max(0.0, 100.0 * (1.0 - gap))
        return gap, fairness

    def cba(a_out: int, b_out: int, n_a: int, n_b: int) -> tuple[bool, int, int]:
        a_max_in = max_incoming_salary(a_out, tier_a)
        b_max_in = max_incoming_salary(b_out, tier_b)
        # Side A receives what B sends out
        a_legal = b_out <= a_max_in
        b_legal = a_out <= b_max_in
        if tier_a == "second_apron" and n_a > 1:
            a_legal = False
        if tier_b == "second_apron" and n_b > 1:
            b_legal = False
        return (a_legal and b_legal), a_max_in, b_max_in

    base_gap, base_fairness = score(anchored_a_tvs, anchored_b_tvs)
    base_legal, base_a_max_in, base_b_max_in = cba(
        anchored_a_salary,
        anchored_b_salary,
        len(anchor_a_players),
        len(anchor_b_players),
    )

    as_entered = {
        "a_tvs": round(anchored_a_tvs, 1),
        "b_tvs": round(anchored_b_tvs, 1),
        "gap_pct": round(base_gap * 100, 1),
        "fairness_score": round(base_fairness, 1),
        "cba_legal": base_legal,
        "a_salary_out": anchored_a_salary,
        "b_salary_out": anchored_b_salary,
        "a_max_salary_in": base_a_max_in,
        "b_max_salary_in": base_b_max_in,
    }

    # Determine the deficit side — the one most additions go on. Bilateral
    # search still allows up to `max_additions` per side, capped by total
    # `max_additions` across both sides combined.
    deficit_is_a = anchored_a_tvs < anchored_b_tvs
    anchored_ids = {p.id for p in anchor_a_players + anchor_b_players} | {
        pk.id for pk in anchor_a_picks + anchor_b_picks
    }
    excluded_set = set(excluded_player_ids or [])
    mle_a = mle_amount(tier_a)
    mle_b = mle_amount(tier_b)

    def build_pool(team_id: str) -> tuple[list[Player], list, dict, dict]:
        players = [
            p for p in repo.list_players()
            if p.team_id == team_id
            and p.id not in anchored_ids
            and p.id not in excluded_set
        ]
        picks = [
            pk for pk in repo.list_picks()
            if pk.owner_team_id == team_id and pk.id not in anchored_ids
        ]
        pl_tvs = {p.id: _player_tvs(p, rubric) for p in players}
        pk_tvs = {pk.id: pick_value(pk) for pk in picks}
        return players, picks, pl_tvs, pk_tvs

    a_players, a_picks, a_player_tvs, a_pick_tvs = build_pool(team_a_id)
    b_players, b_picks, b_player_tvs, b_pick_tvs = build_pool(team_b_id)

    def enumerate_side_combos(
        players: list[Player],
        picks: list,
        player_tvs: dict,
        pick_tvs: dict,
        max_n: int,
    ) -> list[tuple[tuple, tuple, float, int]]:
        """Returns [(player_combo, pick_combo, total_tvs, total_player_salary), ...]."""
        out: list[tuple[tuple, tuple, float, int]] = []
        for n_pl in range(max_n + 1):
            for pl_combo in combinations(players, n_pl):
                pl_tvs_sum = sum(player_tvs[p.id] for p in pl_combo)
                pl_sal_sum = sum(p.contract.current_salary for p in pl_combo)
                for n_pk in range(max_n + 1 - n_pl):
                    for pk_combo in combinations(picks, n_pk):
                        pk_tvs_sum = sum(pick_tvs[pk.id] for pk in pk_combo)
                        out.append(
                            (pl_combo, pk_combo, pl_tvs_sum + pk_tvs_sum, pl_sal_sum)
                        )
        return out

    # Bilateral search: the deficit side (whichever has lower anchored TVS) is
    # allowed up to `max_additions` pieces. The SURPLUS side is capped at 1
    # "sweetener" piece — enough to handle the "throw in one player to balance
    # this" case without combinatorially exploding the search space.
    a_max = max_additions if deficit_is_a else 1
    b_max = max_additions if not deficit_is_a else 1
    a_combos = enumerate_side_combos(a_players, a_picks, a_player_tvs, a_pick_tvs, a_max)
    b_combos = enumerate_side_combos(b_players, b_picks, b_player_tvs, b_pick_tvs, b_max)

    def cba_with_mle(
        a_out: int, b_out: int, n_a: int, n_b: int
    ) -> tuple[bool, int, int, int, int]:
        """Returns (legal, a_max_in_effective, b_max_in_effective, mle_used_a, mle_used_b)."""
        a_max_in_base = max_incoming_salary(a_out, tier_a)
        b_max_in_base = max_incoming_salary(b_out, tier_b)
        # Try without MLE first
        a_short = max(0, b_out - a_max_in_base)
        b_short = max(0, a_out - b_max_in_base)
        # Apply MLE only if it fully closes the shortfall (MLE is indivisible)
        mle_used_a = mle_a if 0 < a_short <= mle_a else 0
        mle_used_b = mle_b if 0 < b_short <= mle_b else 0
        a_legal = b_out <= a_max_in_base + mle_used_a
        b_legal = a_out <= b_max_in_base + mle_used_b
        # Second-apron blocks aggregation and MLE usage
        if tier_a == "second_apron":
            if n_a > 1:
                a_legal = False
            mle_used_a = 0
        if tier_b == "second_apron":
            if n_b > 1:
                b_legal = False
            mle_used_b = 0
        return (
            a_legal and b_legal,
            a_max_in_base + mle_used_a,
            b_max_in_base + mle_used_b,
            mle_used_a,
            mle_used_b,
        )

    results: list[dict] = []
    for a_pl_combo, a_pk_combo, a_added_tvs, a_added_sal in a_combos:
        a_size = len(a_pl_combo) + len(a_pk_combo)
        for b_pl_combo, b_pk_combo, b_added_tvs, b_added_sal in b_combos:
            b_size = len(b_pl_combo) + len(b_pk_combo)
            total_added = a_size + b_size
            if total_added == 0:
                continue
            if total_added > max_additions:
                continue

            a_tvs_final = anchored_a_tvs + a_added_tvs
            b_tvs_final = anchored_b_tvs + b_added_tvs
            a_sal_final = anchored_a_salary + a_added_sal
            b_sal_final = anchored_b_salary + b_added_sal
            n_a = len(anchor_a_players) + len(a_pl_combo)
            n_b = len(anchor_b_players) + len(b_pl_combo)

            gap, fairness = score(a_tvs_final, b_tvs_final)
            if gap > fair_gap_threshold:
                continue

            legal, a_max_in, b_max_in, mle_used_a, mle_used_b = cba_with_mle(
                a_sal_final, b_sal_final, n_a, n_b
            )

            additions: list[dict] = []
            for p in a_pl_combo:
                d = _asset_dict_player(p, a_player_tvs[p.id])
                d["from_team_id"] = team_a_id
                additions.append(d)
            for pk in a_pk_combo:
                d = _asset_dict_pick(pk, a_pick_tvs[pk.id])
                d["from_team_id"] = team_a_id
                additions.append(d)
            for p in b_pl_combo:
                d = _asset_dict_player(p, b_player_tvs[p.id])
                d["from_team_id"] = team_b_id
                additions.append(d)
            for pk in b_pk_combo:
                d = _asset_dict_pick(pk, b_pick_tvs[pk.id])
                d["from_team_id"] = team_b_id
                additions.append(d)

            # "additions_for" retains the team contributing the LARGER share
            # of additions (the side getting filled). Used for legacy UI text.
            primary_team = team_a_id if a_size > b_size else team_b_id

            results.append(
                {
                    "additions_for": primary_team,
                    "additions": additions,
                    "n_additions": total_added,
                    "additions_a_count": a_size,
                    "additions_b_count": b_size,
                    "a_tvs": round(a_tvs_final, 1),
                    "b_tvs": round(b_tvs_final, 1),
                    "gap_pct": round(gap * 100, 1),
                    "fairness_score": round(fairness, 1),
                    "a_salary_out": a_sal_final,
                    "b_salary_out": b_sal_final,
                    "a_max_salary_in": a_max_in,
                    "b_max_salary_in": b_max_in,
                    "cba_legal": legal,
                    "mle_used_a": mle_used_a,
                    "mle_used_b": mle_used_b,
                }
            )

    # Prefer legal, then fewest additions, then closest gap.
    results.sort(key=lambda r: (not r["cba_legal"], r["n_additions"], r["gap_pct"]))

    anchor_a_assets = [
        _asset_dict_player(p, anchor_player_tvs[p.id]) for p in anchor_a_players
    ] + [_asset_dict_pick(pk, anchor_pick_tvs[pk.id]) for pk in anchor_a_picks]
    anchor_b_assets = [
        _asset_dict_player(p, anchor_player_tvs[p.id]) for p in anchor_b_players
    ] + [_asset_dict_pick(pk, anchor_pick_tvs[pk.id]) for pk in anchor_b_picks]

    # Stamp the (single-team) team_b_id on every suggestion for UI consistency
    # with league-wide mode.
    for r in results:
        r["team_b_id"] = team_b_id

    # Apply return-preferences filter in single-team mode too (same OR semantics
    # as league-wide, gated to the same predicate).
    if return_preferences:
        results = [
            r for r in results
            if _suggestion_matches_preferences(
                r,
                return_preferences,
                repo,
                rubric,
                picks_min_count=picks_min_count,
                picks_years=picks_years or [],
                picks_round=picks_round,
            )
        ]

    return {
        "team_a_id": team_a_id,
        "team_b_id": team_b_id,
        "team_a_tax_tier": tier_a,
        "team_a_tax_tier_label": TIER_LABEL[tier_a],
        "team_b_tax_tier": tier_b,
        "team_b_tax_tier_label": TIER_LABEL[tier_b],
        "anchors_a": anchor_a_assets,
        "anchors_b": anchor_b_assets,
        "as_entered": as_entered,
        "deficit_side": "a" if deficit_is_a else "b",
        "league_wide": False,
        "suggestions": results[:limit],
    }


def _find_balancing_across_league(
    team_a_id: str,
    anchors_a: list[dict],
    anchors_b: list[dict],
    repo: Repository,
    max_additions: int,
    limit: int,
    return_preferences: list[str],
    picks_min_count: int = 1,
    picks_years: list[int] | None = None,
    picks_round: int | None = None,
    excluded_player_ids: list[str] | None = None,
    fair_gap_threshold: float = FAIR_GAP,
) -> dict:
    """League-wide variant of find_balancing_additions.

    Iterates every team other than Side A's, runs the standard single-team
    search against each, and merges the suggestions into one ranked list.
    """
    if not anchors_a:
        raise ValueError("Side A must have anchored assets for a league-wide search")
    if anchors_b:
        raise ValueError("Cannot anchor Side B assets when team_b_id is unspecified")

    team_a = repo.get_team(team_a_id)
    if not team_a:
        raise ValueError(f"Unknown team_id: {team_a_id}")

    rubric = repo.get_rubric()
    tier_a = team_tax_tier(team_a_id, repo)

    # Resolve and value Side A anchors once for the response envelope.
    anchor_a_players, anchor_a_picks = _resolve_anchors(anchors_a, team_a_id, repo)
    anchor_player_tvs = {p.id: _player_tvs(p, rubric) for p in anchor_a_players}
    anchor_pick_tvs = {pk.id: pick_value(pk) for pk in anchor_a_picks}
    anchor_a_assets = [
        _asset_dict_player(p, anchor_player_tvs[p.id]) for p in anchor_a_players
    ] + [_asset_dict_pick(pk, anchor_pick_tvs[pk.id]) for pk in anchor_a_picks]

    invalid = [p for p in return_preferences if p not in VALID_RETURN_PREFERENCES]
    if invalid:
        raise ValueError(
            f"Unknown return_preferences: {invalid}. "
            f"Valid: {sorted(VALID_RETURN_PREFERENCES)}"
        )

    from concurrent.futures import ThreadPoolExecutor

    candidate_team_ids = [t.id for t in repo.list_teams() if t.id != team_a_id]

    def search_one(other_id: str) -> list[dict]:
        try:
            sub = find_balancing_additions(
                team_a_id,
                other_id,
                anchors_a,
                [],
                repo,
                max_additions,
                limit=limit,
                excluded_player_ids=excluded_player_ids,
                fair_gap_threshold=fair_gap_threshold,
            )
            return sub["suggestions"]
        except ValueError:
            return []

    merged: list[dict] = []
    # The per-team search is CPU-bound but small; the GIL releases during
    # repo lookups and pydantic operations. Thread pool gives a real speedup
    # for league-wide scans (~5x over sequential in practice).
    with ThreadPoolExecutor(max_workers=min(8, max(2, len(candidate_team_ids)))) as ex:
        for sub_results in ex.map(search_one, candidate_team_ids):
            merged.extend(sub_results)

    if return_preferences:
        merged = [
            s for s in merged
            if _suggestion_matches_preferences(
                s,
                return_preferences,
                repo,
                rubric,
                picks_min_count=picks_min_count,
                picks_years=picks_years or [],
                picks_round=picks_round,
            )
        ]

    # Re-rank merged results globally.
    merged.sort(key=lambda r: (not r["cba_legal"], r["n_additions"], r["gap_pct"]))

    return {
        "team_a_id": team_a_id,
        "team_b_id": None,
        "team_a_tax_tier": tier_a,
        "team_a_tax_tier_label": TIER_LABEL[tier_a],
        "team_b_tax_tier": None,
        "team_b_tax_tier_label": None,
        "anchors_a": anchor_a_assets,
        "anchors_b": [],
        "as_entered": None,
        "deficit_side": "b",
        "league_wide": True,
        "return_preferences": return_preferences,
        "picks_filter": {
            "min_count": picks_min_count,
            "years": picks_years or [],
            "round": picks_round,
        } if "picks" in return_preferences else None,
        "suggestions": merged[:limit],
    }
