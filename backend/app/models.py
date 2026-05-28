from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Position = Literal["PG", "SG", "SF", "PF", "C"]


class PlayerStats(BaseModel):
    season: str
    games_played: int
    minutes_per_game: float
    points: float
    rebounds: float
    assists: float
    steals: float = 0.0
    blocks: float = 0.0
    turnovers: float = 0.0
    fg_pct: float = 0.0
    three_pct: float = 0.0
    ft_pct: float = 0.0
    fta_per_game: float = 0.0
    three_attempts_per_game: float = 0.0
    epm: float = Field(description="Estimated Plus-Minus (BPM substitute when EPM unavailable)")
    bpm: float = Field(description="Box Plus-Minus")
    obpm: float = Field(default=0.0, description="Offensive BPM")
    dbpm: float = Field(default=0.0, description="Defensive BPM")
    vorp: float = Field(description="Value Over Replacement Player")
    per: float = Field(default=0.0, description="Player Efficiency Rating")
    usg_pct: float = Field(default=0.0, description="Usage rate %")
    ts_pct: float = Field(default=0.0, description="True shooting %")
    efg_pct: float = Field(default=0.0, description="Effective field goal %")
    ast_pct: float = Field(default=0.0, description="Assist %")
    tov_pct: float = Field(default=0.0, description="Turnover %")
    all_nba: bool = False
    all_star: bool = False


class Contract(BaseModel):
    current_salary: int = Field(default=0, description="Current-year cap hit in dollars")
    total_guaranteed: int = Field(default=0, description="Total guaranteed dollars remaining")
    years_remaining: int = Field(default=0, description="Years left including current")


class SeasonLog(BaseModel):
    """One season's actual stats — kept alongside the blended `stats` for transparency."""

    season: str
    games_played: int
    minutes_per_game: float
    points: float
    rebounds: float
    assists: float
    bpm: float
    vorp: float
    ts_pct: float = 0.0
    usg_pct: float = 0.0


class Player(BaseModel):
    id: str
    name: str
    team_id: str
    position: Position
    age: int
    stats: PlayerStats
    contract: Contract = Field(default_factory=lambda: Contract())
    archetype: str | None = None
    season_logs: list[SeasonLog] = Field(
        default_factory=list,
        description="Most recent seasons (descending). Used for multi-year blending.",
    )
    injury_discount: float = Field(
        default=1.0,
        description="Multiplier applied to TVS for missed-time risk (1.0 = no discount, 0.85 = significant injury).",
    )
    total_value: float = Field(
        default=0.0,
        description="Computed TVS — populated by route layer for display in roster cards.",
    )


class DraftPick(BaseModel):
    id: str
    owner_team_id: str
    origin_team_id: str
    year: int
    round: Literal[1, 2]
    protections: str | None = None
    expected_pick: float = Field(
        description="Expected pick number based on origin team's outlook (1-60). "
        "For swap picks, this is the projected swap outcome (better of / worse of)."
    )
    swap_type: Literal["best_of", "worst_of"] | None = Field(
        default=None,
        description="If set, this pick is a swap result. 'best_of' = receives the lower pick "
        "number of the swap partners; 'worst_of' = receives the higher pick number.",
    )
    swap_partners: list[str] = Field(
        default_factory=list,
        description="Team abbreviations of the other teams in the swap (e.g. ['PHX'] for a HOU/PHX swap).",
    )


class TradeException(BaseModel):
    """A real-world Trade Exception (TPE) the team is currently holding.

    Created when a team sends out more salary than it takes back in a non-
    simultaneous trade. Can be used in a later trade to absorb up to (amount)
    of incoming salary without matching outgoing salary. Indivisible —
    a $15M TPE absorbs ONE incoming player up to $15M, not split across two.

    MLE slots are derived from the team's tax tier at evaluation time and are
    not stored here.
    """

    id: str
    label: str = Field(description="Human-readable origin, e.g. 'from Brogdon trade'")
    amount: int = Field(description="Available absorption capacity in dollars")
    expires: str | None = Field(
        default=None,
        description="Expiration date or season label (informational; not enforced)",
    )


class Team(BaseModel):
    id: str
    name: str
    abbreviation: str
    needs: list[Position] = Field(default_factory=list)
    timeline: Literal["contender", "play_in", "rebuild"] = "play_in"
    trade_exceptions: list[TradeException] = Field(default_factory=list)


class TierRule(BaseModel):
    """One rule in a tier rubric. All conditions must match for the rule to fire."""

    tier: int = Field(ge=1, le=7)
    label: str
    min_stats_value: float | None = Field(
        default=None,
        description="Min composite stats_value (multi-subscore production rating with age-gated peak boost). Preferred over min_epm.",
    )
    min_epm: float | None = None
    min_bpm: float | None = None
    min_vorp: float | None = None
    min_age: int | None = None
    max_age: int | None = None
    requires_all_nba: bool = False
    requires_all_star: bool = False


class TierRubric(BaseModel):
    """Ordered rules. First match wins; player not matching any falls to default_tier."""

    name: str
    rules: list[TierRule]
    default_tier: int = 7
    multipliers: dict[int, float] = Field(
        description="Tier number -> multiplier applied to stats value",
    )


class TradeAsset(BaseModel):
    """One asset moving between teams. Either player_id or pick_id is set.

    destination_team_id is required for 3+ team trades (each asset needs an
    explicit recipient). For 2-team trades it's optional — if omitted, the
    engine routes the asset to the only other side.
    """

    player_id: str | None = None
    pick_id: str | None = None
    destination_team_id: str | None = None


class TradeSide(BaseModel):
    team_id: str
    sending: list[TradeAsset]
    using_exceptions: list[str] = Field(
        default_factory=list,
        description=(
            "IDs of this team's own TPEs / MLE slots being applied as incoming-salary "
            "absorption. Use 'TEAM-MLE' for the team's auto-derived MLE slot, or any "
            "id from the team's trade_exceptions list."
        ),
    )


class Trade(BaseModel):
    sides: list[TradeSide] = Field(min_length=2, max_length=4)


class SubscoreBreakdown(BaseModel):
    """Per-subscore contributions to the player's raw production rating."""

    production: float = 0.0
    efficiency: float = 0.0
    impact: float = 0.0
    two_way: float = 0.0
    playmaking_bonus: float = 0.0
    minutes_adjustment: float = 0.0
    turnover_penalty: float = 0.0
    free_throw_bonus: float = 0.0


class AssetValuation(BaseModel):
    label: str
    kind: Literal["player", "pick"]
    stats_value: float
    subscores: SubscoreBreakdown | None = None
    archetype: str | None = None
    tier: int | None = None
    tier_label: str | None = None
    tier_multiplier: float = 1.0
    contract_adjustment: float = Field(
        default=0.0,
        description="TVS bonus/penalty from contract surplus (positive = team-friendly deal)",
    )
    current_salary: int = 0
    fit_bonus: float = 0.0
    total_value: float


class SideValuation(BaseModel):
    team_id: str
    sending: list[AssetValuation]
    receiving: list[AssetValuation]
    sending_total: float
    receiving_total: float
    net: float = Field(description="receiving_total - sending_total")


class CBASideCheck(BaseModel):
    team_id: str
    tax_tier: Literal["under_cap", "over_cap", "luxury_tax", "first_apron", "second_apron"]
    tax_tier_label: str
    total_team_salary: int = Field(description="Sum of all roster current salaries")
    salary_out: int = Field(description="Sum of outgoing player salaries in this trade")
    salary_in: int = Field(description="Sum of incoming player salaries in this trade")
    max_salary_in: int = Field(description="Largest legal incoming salary per CBA rules")
    legal: bool
    warnings: list[str]
    n_players_sent: int
    exception_absorption: int = Field(
        default=0,
        description="Sum of TPE/MLE capacity applied to absorb incoming salary on this side.",
    )
    exceptions_used: list[str] = Field(
        default_factory=list,
        description="IDs of TPE/MLE entries applied as absorption on this side.",
    )
    created_tpe: int = Field(
        default=0,
        description="New Trade Exception that this trade would create for the team (positive = net salary sent out).",
    )


class FairnessReport(BaseModel):
    sides: list[SideValuation]
    fairness_score: float = Field(
        ge=0,
        le=100,
        description="100 = perfectly even; lower = more lopsided",
    )
    verdict: Literal["fair", "slightly_uneven", "lopsided", "very_lopsided"]
    explanation: list[str]
    cba_legal: bool = Field(
        default=True,
        description="Overall CBA legality — true only if every side passes salary-match + apron rules.",
    )
    cba_sides: list[CBASideCheck] = Field(default_factory=list)
