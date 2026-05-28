export type Position = "PG" | "SG" | "SF" | "PF" | "C";
export type Timeline = "contender" | "play_in" | "rebuild";
export type Verdict = "fair" | "slightly_uneven" | "lopsided" | "very_lopsided";

export interface PlayerStats {
  season: string;
  games_played: number;
  minutes_per_game: number;
  points: number;
  rebounds: number;
  assists: number;
  epm: number;
  bpm: number;
  vorp: number;
  all_nba: boolean;
  all_star: boolean;
}

export interface Contract {
  current_salary: number;
  total_guaranteed: number;
  years_remaining: number;
}

export interface SeasonLog {
  season: string;
  games_played: number;
  minutes_per_game: number;
  points: number;
  rebounds: number;
  assists: number;
  bpm: number;
  vorp: number;
  ts_pct: number;
  usg_pct: number;
}

export interface Player {
  id: string;
  name: string;
  team_id: string;
  position: Position;
  age: number;
  stats: PlayerStats;
  contract: Contract;
  archetype: string | null;
  season_logs: SeasonLog[];
  injury_discount: number;
  total_value?: number;
}

export interface DraftPick {
  id: string;
  owner_team_id: string;
  origin_team_id: string;
  year: number;
  round: 1 | 2;
  protections: string | null;
  expected_pick: number;
}

export interface Team {
  id: string;
  name: string;
  abbreviation: string;
  needs: Position[];
  timeline: Timeline;
}

export interface TradeAsset {
  player_id?: string;
  pick_id?: string;
}

export interface TradeSide {
  team_id: string;
  sending: TradeAsset[];
}

export interface SubscoreBreakdown {
  production: number;
  efficiency: number;
  impact: number;
  two_way: number;
  playmaking_bonus: number;
  minutes_adjustment: number;
  turnover_penalty: number;
  free_throw_bonus: number;
}

export interface AssetValuation {
  label: string;
  kind: "player" | "pick";
  stats_value: number;
  subscores: SubscoreBreakdown | null;
  archetype: string | null;
  tier: number | null;
  tier_label: string | null;
  tier_multiplier: number;
  contract_adjustment: number;
  current_salary: number;
  fit_bonus: number;
  total_value: number;
}

export interface SideValuation {
  team_id: string;
  sending: AssetValuation[];
  receiving: AssetValuation[];
  sending_total: number;
  receiving_total: number;
  net: number;
}

export type TaxTier =
  | "under_cap"
  | "over_cap"
  | "luxury_tax"
  | "first_apron"
  | "second_apron";

export interface CBASideCheck {
  team_id: string;
  tax_tier: TaxTier;
  tax_tier_label: string;
  total_team_salary: number;
  salary_out: number;
  salary_in: number;
  max_salary_in: number;
  legal: boolean;
  warnings: string[];
  n_players_sent: number;
}

export interface RankedPlayer {
  id: string;
  name: string;
  team_id: string;
  position: Position;
  age: number;
  archetype: string | null;
  tier: number;
  tier_label: string;
  tier_multiplier: number;
  stats_value: number;
  injury_discount: number;
  tier_adjusted: number;
  contract_adjustment: number;
  current_salary: number;
  years_remaining: number;
  total_value: number;
  bpm: number;
  vorp: number;
  bpm_2yr: number;
  bpm_5yr: number;
  trend_ratio: number;
  rank: number;
}

export interface FairnessReport {
  sides: SideValuation[];
  fairness_score: number;
  verdict: Verdict;
  explanation: string[];
  cba_legal: boolean;
  cba_sides: CBASideCheck[];
}

export interface PlayerBreakdown {
  id: string;
  name: string;
  team_id: string;
  position: Position;
  age: number;
  archetype: string | null;
  tier: number;
  tier_label: string;
  tier_multiplier: number;
  injury_discount: number;
  components: {
    subscores: { production: number; efficiency: number; impact: number; two_way: number };
    subscore_weights: { production: number; efficiency: number; impact: number; two_way: number };
    bonuses: { playmaking: number; minutes: number; free_throw: number; turnover_penalty: number };
    weighted_raw: number;
    multipliers: {
      position: number;
      age_curve: number;
      youth_premium: number;
      durability: number;
      consistency: number;
    };
    stats_value: number;
  };
  tier_adjusted: number;
  contract_adjustment: number;
  current_salary: number;
  total_guaranteed: number;
  years_remaining: number;
  total_value: number;
  stats: PlayerStats;
  season_logs: SeasonLog[];
  trend_ratio: number;
}

export interface FinderAsset {
  kind: "player" | "pick";
  id: string;
  name: string;
  tvs: number;
}

export interface FinderPackage {
  assets: FinderAsset[];
  package_tvs: number;
  gap_pct: number;
  salary_out: number;
  salary_in: number;
  max_salary_in: number;
  cba_legal: boolean;
  n_assets: number;
}

export interface TradeFinderResult {
  target: { id: string; name: string; team_id: string; tvs: number; salary: number };
  acquiring_team_id: string;
  acquirer_tax_tier: string;
  acquirer_tax_tier_label: string;
  packages: FinderPackage[];
}
