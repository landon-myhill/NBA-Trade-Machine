import type {
  DraftPick,
  FairnessReport,
  Player,
  PlayerBreakdown,
  RankedPlayer,
  Team,
  TradeFinderResult,
  TradeSide,
} from "../types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listTeams: () => request<Team[]>("/teams"),
  getRoster: (teamId: string) =>
    request<Player[]>(`/teams/${teamId}/roster`),
  getPicks: (teamId: string) =>
    request<DraftPick[]>(`/teams/${teamId}/picks`),
  evaluate: (sides: TradeSide[]) =>
    request<FairnessReport>("/trades/evaluate", {
      method: "POST",
      body: JSON.stringify({ sides }),
    }),
  rankedPlayers: () => request<RankedPlayer[]>("/players/ranked"),
  breakdown: (playerId: string) =>
    request<PlayerBreakdown>(`/players/${playerId}/breakdown`),
  findTrades: (targetId: string, teamId: string) =>
    request<TradeFinderResult>(
      `/trades/find?target=${targetId}&team=${teamId}`
    ),
};
