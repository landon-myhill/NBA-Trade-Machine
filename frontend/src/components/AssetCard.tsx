import type { DraftPick, Player } from "../types";

interface PlayerCardProps {
  player: Player;
  selected: boolean;
  onToggle: () => void;
}

function formatSalary(dollars: number): string {
  if (!dollars) return "";
  const m = dollars / 1_000_000;
  return m >= 10 ? `$${m.toFixed(0)}M` : `$${m.toFixed(1)}M`;
}

export function PlayerCard({ player, selected, onToggle }: PlayerCardProps) {
  const c = player.contract;
  const salaryStr =
    c.current_salary > 0
      ? ` · ${formatSalary(c.current_salary)}/yr × ${c.years_remaining}yr`
      : "";
  const archetypeStr = player.archetype ? ` · ${player.archetype}` : "";
  const hurt = player.injury_discount < 0.95;
  const tvs = (player as Player & { total_value?: number }).total_value ?? 0;
  return (
    <div
      className={`asset-card${selected ? " selected" : ""}`}
      onClick={onToggle}
    >
      <div style={{ flex: 1 }}>
        <strong>
          {player.name}
          {hurt && (
            <span
              title={`Injury discount: ${(player.injury_discount * 100).toFixed(0)}% (multi-year blended)`}
              style={{
                marginLeft: "0.4rem",
                fontSize: "0.7rem",
                color: "var(--warn)",
              }}
            >
              ⚕
            </span>
          )}
        </strong>
        <div className="meta">
          {player.position} · age {player.age}
          {archetypeStr}
          {salaryStr}
        </div>
      </div>
      <div
        style={{
          fontWeight: 700,
          fontSize: "1rem",
          fontVariantNumeric: "tabular-nums",
          color: tvs >= 80 ? "var(--good)" : tvs >= 40 ? "var(--accent)" : "var(--muted)",
        }}
        title="Trade Value Score (TVS)"
      >
        {tvs.toFixed(1)}
      </div>
    </div>
  );
}

interface PickCardProps {
  pick: DraftPick;
  selected: boolean;
  onToggle: () => void;
}

export function PickCard({ pick, selected, onToggle }: PickCardProps) {
  const via =
    pick.origin_team_id !== pick.owner_team_id
      ? ` via ${pick.origin_team_id}`
      : "";
  const protections = pick.protections ? ` · ${pick.protections}` : "";
  return (
    <div
      className={`asset-card${selected ? " selected" : ""}`}
      onClick={onToggle}
    >
      <div>
        <strong>
          {pick.year} R{pick.round}
        </strong>
        <div className="meta">
          exp. #{Math.round(pick.expected_pick)}
          {via}
          {protections}
        </div>
      </div>
    </div>
  );
}
