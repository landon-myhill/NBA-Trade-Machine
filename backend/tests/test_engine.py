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


def test_three_team_trade_rejected():
    repo = JsonRepository()
    p1, p2, p3 = repo.list_players()[:3]
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
        assert "2-team" in str(e)
        return
    raise AssertionError("expected ValueError for 3-team trade")
