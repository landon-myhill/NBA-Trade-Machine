from app.data.repository import JsonRepository
from app.fairness.tier import assign_tier


def test_jokic_is_tier_one():
    repo = JsonRepository()
    rubric = repo.get_rubric()
    jokic = repo.get_player("jokicni01")
    assert jokic is not None
    tier, _ = assign_tier(jokic, rubric)
    assert tier == 1


def test_default_tier_for_deep_bench():
    """A player with very low BPM AND minimal minutes should fall to default tier."""
    repo = JsonRepository()
    rubric = repo.get_rubric()
    # find a player who fails both composite (low minutes/volume) AND BPM
    deep_bench = next(
        (
            p
            for p in repo.list_players()
            if p.stats.bpm < -2.5 and p.stats.minutes_per_game < 12
        ),
        None,
    )
    if deep_bench is None:
        # Fall back: at least confirm SOMEONE is in the default tier
        defaulted = [p for p in repo.list_players() if assign_tier(p, rubric)[0] == rubric.default_tier]
        assert len(defaulted) > 0
        return
    tier, _ = assign_tier(deep_bench, rubric)
    assert tier == rubric.default_tier


def test_tier_assignment_is_monotonic_in_bpm():
    """Higher-BPM players should land in tiers <= lower-BPM players' tiers."""
    repo = JsonRepository()
    rubric = repo.get_rubric()
    jokic = repo.get_player("jokicni01")
    deep_bench = next(
        (p for p in repo.list_players() if p.stats.bpm < -2.0),
        None,
    )
    assert jokic and deep_bench
    t_top, _ = assign_tier(jokic, rubric)
    t_low, _ = assign_tier(deep_bench, rubric)
    assert t_top < t_low


def test_accolades_do_not_affect_tier():
    """The rubric has no all_star/all_nba gates — accolades carry no tier weight."""
    repo = JsonRepository()
    rubric = repo.get_rubric()
    # No tier rule in the live rubric should require an accolade
    for rule in rubric.rules:
        assert not rule.requires_all_star
        assert not rule.requires_all_nba
