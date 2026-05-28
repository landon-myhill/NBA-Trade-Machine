import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DraftPick, Player, Team, TradeAsset } from "../types";
import { PickCard, PlayerCard } from "./AssetCard";

interface Props {
  teams: Team[];
  selectedTeamId: string | null;
  onTeamChange: (teamId: string) => void;
  sending: TradeAsset[];
  onToggleAsset: (asset: TradeAsset) => void;
  excludeTeamId: string | null;
}

export function TeamPanel({
  teams,
  selectedTeamId,
  onTeamChange,
  sending,
  onToggleAsset,
  excludeTeamId,
}: Props) {
  const [roster, setRoster] = useState<Player[]>([]);
  const [picks, setPicks] = useState<DraftPick[]>([]);

  useEffect(() => {
    if (!selectedTeamId) {
      setRoster([]);
      setPicks([]);
      return;
    }
    Promise.all([
      api.getRoster(selectedTeamId),
      api.getPicks(selectedTeamId),
    ]).then(([r, p]) => {
      setRoster(r);
      setPicks(p);
    });
  }, [selectedTeamId]);

  const isSelected = (asset: TradeAsset) =>
    sending.some(
      (a) =>
        (asset.player_id && a.player_id === asset.player_id) ||
        (asset.pick_id && a.pick_id === asset.pick_id)
    );

  return (
    <div className="panel">
      <h2>Team</h2>
      <select
        value={selectedTeamId ?? ""}
        onChange={(e) => onTeamChange(e.target.value)}
      >
        <option value="" disabled>
          Select a team…
        </option>
        {teams
          .filter((t) => t.id !== excludeTeamId)
          .map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
      </select>

      {selectedTeamId && (() => {
        const team = teams.find((t) => t.id === selectedTeamId);
        if (!team) return null;
        const TIMELINE_LABEL: Record<string, string> = {
          contender: "Contender",
          play_in: "Play-In",
          rebuild: "Rebuild",
        };
        return (
          <div className="team-context">
            <span className={`timeline-pill ${team.timeline}`}>
              {TIMELINE_LABEL[team.timeline] ?? team.timeline}
            </span>
            <span className="meta" style={{ marginLeft: "0.5rem" }}>
              Needs:{" "}
              {team.needs.length > 0 ? team.needs.join(", ") : "balanced roster"}
            </span>
          </div>
        );
      })()}

      {selectedTeamId && (() => {
        // Under contract (2+ yrs) = main roster; expiring/no-deal = free agents
        const underContract = roster.filter((p) => p.contract.years_remaining >= 2);
        const freeAgents = roster.filter((p) => p.contract.years_remaining < 2);
        return (
          <>
            <h3>Roster</h3>
            <div className="asset-list">
              {underContract.map((p) => (
                <PlayerCard
                  key={p.id}
                  player={p}
                  selected={isSelected({ player_id: p.id })}
                  onToggle={() => onToggleAsset({ player_id: p.id })}
                />
              ))}
            </div>

            <h3>Picks</h3>
            <div className="asset-list">
              {picks.length === 0 && (
                <div className="meta" style={{ color: "var(--muted)" }}>
                  No tradeable picks in seed data.
                </div>
              )}
              {picks.map((p) => (
                <PickCard
                  key={p.id}
                  pick={p}
                  selected={isSelected({ pick_id: p.id })}
                  onToggle={() => onToggleAsset({ pick_id: p.id })}
                />
              ))}
            </div>

            {freeAgents.length > 0 && (
              <details className="fa-section">
                <summary>
                  Free agents · sign &amp; trade ({freeAgents.length})
                </summary>
                <div className="asset-list" style={{ marginTop: "0.5rem" }}>
                  {freeAgents.map((p) => (
                    <PlayerCard
                      key={p.id}
                      player={p}
                      selected={isSelected({ player_id: p.id })}
                      onToggle={() => onToggleAsset({ player_id: p.id })}
                    />
                  ))}
                </div>
              </details>
            )}
          </>
        );
      })()}
    </div>
  );
}
