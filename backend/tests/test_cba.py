from app.cba.limits import tax_tier
from app.cba.matching import max_incoming_salary, check_side


def test_tax_tiers():
    assert tax_tier(100_000_000) == "under_cap"
    assert tax_tier(160_000_000) == "over_cap"
    assert tax_tier(190_000_000) == "luxury_tax"
    assert tax_tier(200_000_000) == "first_apron"
    assert tax_tier(210_000_000) == "second_apron"


def test_non_taxpayer_matching_brackets():
    # $5M outgoing → 200% + $250K = $10.25M
    assert max_incoming_salary(5_000_000, "under_cap") == 10_250_000
    # $20M outgoing → 175% = $35M
    assert max_incoming_salary(20_000_000, "under_cap") == 35_000_000
    # $40M outgoing → 125% + $250K = $50.25M
    assert max_incoming_salary(40_000_000, "under_cap") == 50_250_000


def test_taxpayer_matching():
    # $20M outgoing → 110% + $100K = $22.1M
    assert max_incoming_salary(20_000_000, "luxury_tax") == 22_100_000
    assert max_incoming_salary(20_000_000, "first_apron") == 22_100_000


def test_second_apron_dollar_for_dollar():
    assert max_incoming_salary(20_000_000, "second_apron") == 20_000_000


def test_legal_simple_swap():
    check = check_side("BOS", "luxury_tax", 30_000_000, 32_000_000, 1)
    assert check.legal
    assert not check.warnings


def test_illegal_overbalanced_taxpayer():
    # Tax team taking back way more
    check = check_side("BOS", "luxury_tax", 20_000_000, 30_000_000, 1)
    assert not check.legal
    assert any("exceeds" in w for w in check.warnings)


def test_second_apron_aggregation_blocked():
    """Aggregating two players is illegal at the second apron, even if dollar math works."""
    check = check_side("PHX", "second_apron", 50_000_000, 50_000_000, 2)
    assert not check.legal
    assert any("aggregate" in w for w in check.warnings)


def test_second_apron_single_player_allowed():
    check = check_side("PHX", "second_apron", 30_000_000, 30_000_000, 1)
    assert check.legal
