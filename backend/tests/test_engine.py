from app.data.repository import JsonRepository
from app.fairness.engine import evaluate
from app.models import Trade, TradeAsset, TradeSide


def _trade(team_a, side_a, team_b, side_b):
    return Trade(
        sides=[
            TradeSide(team_id=team_a, sending=side_a),
            TradeSide(team_id=team_b, sending=side_b),
        ]
    )


def _find_player(repo, name_substring):
    return next(
        p for p in repo.list_players() if name_substring.lower() in p.name.lower()
    )


def test_superstar_for_low_bpm_player_is_lopsided():
    """Trading Jokic for a low-impact role player should be wildly unfair."""
    repo = JsonRepository()
    jokic = _find_player(repo, "jokić")
    role_player = next(
        p
        for p in repo.list_players()
        if p.team_id != jokic.team_id and -2.0 < p.stats.bpm < -0.5 and p.stats.games_played > 30
    )
    trade = _trade(
        team_a=role_player.team_id,
        side_a=[TradeAsset(player_id=role_player.id)],
        team_b=jokic.team_id,
        side_b=[TradeAsset(player_id=jokic.id)],
    )
    report = evaluate(trade, repo)
    assert report.verdict in ("lopsided", "very_lopsided")
    assert report.fairness_score < 75


def test_two_stars_are_closer_to_fair():
    """Two superstar-tier players for each other should score closer to fair."""
    repo = JsonRepository()
    jokic = _find_player(repo, "jokić")
    sga = _find_player(repo, "gilgeous")
    trade = _trade(
        team_a=jokic.team_id,
        side_a=[TradeAsset(player_id=jokic.id)],
        team_b=sga.team_id,
        side_b=[TradeAsset(player_id=sga.id)],
    )
    report = evaluate(trade, repo)
    assert 0 <= report.fairness_score <= 100


def test_pick_only_trade_evaluates():
    repo = JsonRepository()
    pick_a, pick_b = repo.list_picks()[:2]
    trade = _trade(
        team_a=pick_a.owner_team_id,
        side_a=[TradeAsset(pick_id=pick_a.id)],
        team_b=pick_b.owner_team_id,
        side_b=[TradeAsset(pick_id=pick_b.id)],
    )
    report = evaluate(trade, repo)
    assert 0 <= report.fairness_score <= 100


def _three_distinct_team_players(repo):
    """Pick one player from each of three distinct teams (for 3-team trade tests)."""
    seen: dict[str, object] = {}
    for p in repo.list_players():
        if p.team_id not in seen:
            seen[p.team_id] = p
            if len(seen) == 3:
                return list(seen.values())
    raise RuntimeError("Need at least 3 distinct teams in seed data")


def test_three_team_trade_requires_destination():
    repo = JsonRepository()
    p1, p2, p3 = _three_distinct_team_players(repo)
    trade = Trade(
        sides=[
            TradeSide(team_id=p1.team_id, sending=[TradeAsset(player_id=p1.id)]),
            TradeSide(team_id=p2.team_id, sending=[TradeAsset(player_id=p2.id)]),
            TradeSide(team_id=p3.team_id, sending=[TradeAsset(player_id=p3.id)]),
        ]
    )
    try:
        evaluate(trade, repo)
    except ValueError as e:
        assert "destination_team_id" in str(e)
        return
    raise AssertionError("expected ValueError for 3-team trade missing destinations")


def test_creating_tpe_when_sending_more_salary_out():
    repo = JsonRepository()
    players = repo.list_players()
    # Find two players on different teams where A's salary > B's salary by a clear margin.
    by_team: dict = {}
    for p in players:
        if p.contract.current_salary > 0:
            by_team.setdefault(p.team_id, []).append(p)
    team_ids = list(by_team.keys())
    a_player = b_player = None
    for ta in team_ids:
        for tb in team_ids:
            if ta == tb:
                continue
            top_a = max(by_team[ta], key=lambda x: x.contract.current_salary)
            bot_b = min(by_team[tb], key=lambda x: x.contract.current_salary)
            if top_a.contract.current_salary > bot_b.contract.current_salary + 5_000_000:
                a_player, b_player = top_a, bot_b
                break
        if a_player:
            break
    assert a_player and b_player, "Need an asymmetric salary pair in seed data"
    trade = Trade(
        sides=[
            TradeSide(team_id=a_player.team_id, sending=[TradeAsset(player_id=a_player.id)]),
            TradeSide(team_id=b_player.team_id, sending=[TradeAsset(player_id=b_player.id)]),
        ]
    )
    report = evaluate(trade, repo)
    a_side = next(c for c in report.cba_sides if c.team_id == a_player.team_id)
    expected_tpe = a_player.contract.current_salary - b_player.contract.current_salary
    assert a_side.created_tpe == expected_tpe


def test_mle_absorption_unlocks_otherwise_illegal_trade():
    """An over-cap team can absorb a small incoming salary via its non-taxpayer MLE."""
    repo = JsonRepository()
    # Find an over-cap team A and a cheap player on team B (salary < MLE).
    cheap_b = None
    senders = repo.list_players()
    for p in senders:
        if 1_000_000 < p.contract.current_salary < 5_000_000:
            cheap_b = p
            break
    assert cheap_b, "Seed needs at least one cheap-contract player"
    other_team = next(t for t in repo.list_teams() if t.id != cheap_b.team_id)
    # Side A sends NOTHING (no players). Without MLE: salary_out=0 → max_salary_in=$250K. Illegal.
    # With MLE: ~$12.8M absorption → legal.
    trade = Trade(
        sides=[
            TradeSide(
                team_id=other_team.id,
                sending=[],
                using_exceptions=[f"{other_team.id}-MLE"],
            ),
            TradeSide(team_id=cheap_b.team_id, sending=[TradeAsset(player_id=cheap_b.id)]),
        ]
    )
    report = evaluate(trade, repo)
    a_side = next(c for c in report.cba_sides if c.team_id == other_team.id)
    assert a_side.exception_absorption > 0
    assert f"{other_team.id}-MLE" in a_side.exceptions_used


def test_three_team_trade_with_destinations_evaluates():
    repo = JsonRepository()
    p1, p2, p3 = _three_distinct_team_players(repo)
    # Round-robin: p1 -> team2, p2 -> team3, p3 -> team1
    trade = Trade(
        sides=[
            TradeSide(
                team_id=p1.team_id,
                sending=[TradeAsset(player_id=p1.id, destination_team_id=p2.team_id)],
            ),
            TradeSide(
                team_id=p2.team_id,
                sending=[TradeAsset(player_id=p2.id, destination_team_id=p3.team_id)],
            ),
            TradeSide(
                team_id=p3.team_id,
                sending=[TradeAsset(player_id=p3.id, destination_team_id=p1.team_id)],
            ),
        ]
    )
    report = evaluate(trade, repo)
    assert len(report.sides) == 3
    assert 0 <= report.fairness_score <= 100
    # Every team both sends and receives exactly one asset
    for sv in report.sides:
        assert len(sv.sending) == 1
        assert len(sv.receiving) == 1
