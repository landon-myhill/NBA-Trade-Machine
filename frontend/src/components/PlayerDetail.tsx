import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { PlayerBreakdown } from "../types";

function fmtM(d: number): string {
  return d ? `$${(d / 1_000_000).toFixed(1)}M` : "—";
}

function Bar({ label, value, max = 100 }: { label: string; value: number; max?: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div style={{ display: "grid", gridTemplateColumns: "90px 1fr 42px", alignItems: "center", gap: "0.5rem", marginBottom: "0.3rem" }}>
      <span className="meta" style={{ fontSize: "0.8rem" }}>{label}</span>
      <div style={{ height: 6, background: "var(--panel)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: pct >= 70 ? "var(--good)" : pct >= 40 ? "var(--accent)" : "var(--muted)" }} />
      </div>
      <span className="meta" style={{ textAlign: "right", fontSize: "0.8rem" }}>{value.toFixed(0)}</span>
    </div>
  );
}

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "0.25rem 0", fontSize: "0.85rem" }}>
      <span className="meta">{label}</span>
      <span style={{ color: color ?? "var(--text)", fontWeight: 600 }}>{value}</span>
    </div>
  );
}

export function PlayerDetail({ playerId, onClose }: { playerId: string; onClose: () => void }) {
  const [data, setData] = useState<PlayerBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.breakdown(playerId).then(setData).catch((e) => setError(e.message));
  }, [playerId]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>×</button>
        {error && <div className="error">{error}</div>}
        {!data && !error && <div className="meta">Loading…</div>}
        {data && (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem" }}>
              <div>
                <h2 style={{ margin: 0 }}>{data.name}</h2>
                <div className="meta">
                  {data.team_id} · {data.position} · age {data.age}
                  {data.archetype ? ` · ${data.archetype}` : ""}
                </div>
                <div style={{ marginTop: "0.3rem" }}>
                  <span className="tier-pill">T{data.tier} · {data.tier_label}</span>
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: "2.2rem", fontWeight: 800, lineHeight: 1 }}>{data.total_value.toFixed(1)}</div>
                <div className="meta" style={{ fontSize: "0.7rem" }}>TVS</div>
              </div>
            </div>

            <div className="modal-grid">
              <div>
                <h3>Subscores (weighted)</h3>
                <Bar label="Production" value={data.components.subscores.production} />
                <Bar label="Efficiency" value={data.components.subscores.efficiency} />
                <Bar label="Impact" value={data.components.subscores.impact} />
                <Bar label="Two-Way" value={data.components.subscores.two_way} />
                <div className="meta" style={{ fontSize: "0.7rem", marginTop: "0.3rem" }}>
                  weights {Math.round(data.components.subscore_weights.production * 100)}/
                  {Math.round(data.components.subscore_weights.efficiency * 100)}/
                  {Math.round(data.components.subscore_weights.impact * 100)}/
                  {Math.round(data.components.subscore_weights.two_way * 100)}
                </div>

                <h3>Bonuses / penalties</h3>
                <Row label="Playmaking" value={`${data.components.bonuses.playmaking >= 0 ? "+" : ""}${data.components.bonuses.playmaking}`} />
                <Row label="Minutes" value={`${data.components.bonuses.minutes >= 0 ? "+" : ""}${data.components.bonuses.minutes}`} />
                <Row label="Free throw" value={`${data.components.bonuses.free_throw >= 0 ? "+" : ""}${data.components.bonuses.free_throw}`} />
                <Row label="Turnovers" value={`${data.components.bonuses.turnover_penalty}`} />
              </div>

              <div>
                <h3>Multipliers</h3>
                <Row label="Position" value={`×${data.components.multipliers.position}`} />
                <Row label="Age curve" value={`×${data.components.multipliers.age_curve}`} />
                <Row label="Youth premium" value={`×${data.components.multipliers.youth_premium}`} color={data.components.multipliers.youth_premium > 1 ? "var(--good)" : undefined} />
                <Row label="Durability" value={`×${data.components.multipliers.durability}`} />
                <Row label="Consistency" value={`×${data.components.multipliers.consistency}`} color={data.components.multipliers.consistency < 1 ? "var(--bad)" : undefined} />
                <Row label="Injury discount" value={`×${data.injury_discount}`} color={data.injury_discount < 1 ? "var(--warn)" : undefined} />

                <h3>Build-up</h3>
                <Row label="Raw (weighted)" value={`${data.components.weighted_raw}`} />
                <Row label="stats_value" value={`${data.components.stats_value}`} />
                <Row label={`× Tier (×${data.tier_multiplier})`} value={`${data.tier_adjusted}`} />
                <Row label="Contract" value={`${data.contract_adjustment >= 0 ? "+" : ""}${data.contract_adjustment}`} color={data.contract_adjustment >= 0 ? "var(--good)" : "var(--bad)"} />
                <Row label="FINAL TVS" value={`${data.total_value.toFixed(1)}`} />

                <h3>Contract</h3>
                <Row label="Salary" value={`${fmtM(data.current_salary)}/yr × ${data.years_remaining}yr`} />
                <Row label="Guaranteed" value={fmtM(data.total_guaranteed)} />
              </div>
            </div>

            <h3>Recent seasons</h3>
            <div className="season-table">
              {data.season_logs.slice(0, 5).map((log) => (
                <div key={log.season} className="season-row">
                  <span>{log.season}</span>
                  <span className="meta">{log.games_played}g · {log.minutes_per_game.toFixed(0)}mpg</span>
                  <span>{log.points.toFixed(1)}p / {log.rebounds.toFixed(1)}r / {log.assists.toFixed(1)}a</span>
                  <span style={{ textAlign: "right" }}>BPM {log.bpm.toFixed(1)}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
