import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { RankedPlayer, Team, TradeFinderResult } from "../types";

function fmtM(d: number): string {
  return d ? `$${(d / 1_000_000).toFixed(1)}M` : "—";
}

export default function TradeFinder() {
  const [players, setPlayers] = useState<RankedPlayer[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [query, setQuery] = useState("");
  const [target, setTarget] = useState<RankedPlayer | null>(null);
  const [teamId, setTeamId] = useState<string>("");
  const [result, setResult] = useState<TradeFinderResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.rankedPlayers().then(setPlayers).catch((e) => setError(e.message));
    api.listTeams().then(setTeams).catch((e) => setError(e.message));
  }, []);

  const matches = useMemo(() => {
    if (!query.trim()) return [];
    const q = query.toLowerCase();
    return players.filter((p) => p.name.toLowerCase().includes(q)).slice(0, 8);
  }, [query, players]);

  const run = async () => {
    if (!target || !teamId) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.findTrades(target.id, teamId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rankings">
      <h2 style={{ margin: 0 }}>Trade Finder</h2>
      <p className="subtitle">
        Pick a player to acquire and the team trying to get them. The engine finds packages that are
        both fair (within 15% TVS) and CBA-legal.
      </p>

      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="search-wrap" style={{ flex: "1 1 280px" }}>
          <label className="meta" style={{ display: "block", marginBottom: "0.25rem" }}>Target player</label>
          <input
            className="search-input"
            placeholder={target ? target.name : "Search a player…"}
            value={query}
            onChange={(e) => { setQuery(e.target.value); setTarget(null); }}
          />
          {matches.length > 0 && !target && (
            <div className="search-results">
              {matches.map((p) => (
                <div key={p.id} className="search-result" onClick={() => { setTarget(p); setQuery(p.name); }}>
                  <strong>{p.name}</strong>
                  <span style={{ marginLeft: "0.5rem", color: "var(--muted)" }}>{p.team_id} · TVS {p.total_value.toFixed(1)}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div style={{ flex: "0 1 220px" }}>
          <label className="meta" style={{ display: "block", marginBottom: "0.25rem" }}>Acquiring team</label>
          <select value={teamId} onChange={(e) => setTeamId(e.target.value)}>
            <option value="" disabled>Select team…</option>
            {teams.filter((t) => !target || t.id !== target.team_id).map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </div>

        <button onClick={run} disabled={!target || !teamId || loading}>
          {loading ? "Searching…" : "Find Packages"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {result && (
        <div style={{ marginTop: "1rem" }}>
          <div className="meta" style={{ marginBottom: "0.75rem" }}>
            Acquiring <strong style={{ color: "var(--text)" }}>{result.target.name}</strong> (TVS {result.target.tvs}, {fmtM(result.target.salary)}) —
            {" "}{teams.find((t) => t.id === result.acquiring_team_id)?.name} is {result.acquirer_tax_tier_label}
          </div>
          {result.packages.length === 0 && (
            <div className="meta">No fair + legal package found within this team's assets.</div>
          )}
          <div className="ranking-list">
            {result.packages.map((pkg, i) => (
              <div key={i} className="ranking-row" style={{ alignItems: "flex-start" }}>
                <span style={{ width: 40 }}>
                  <span style={{ color: pkg.cba_legal ? "var(--good)" : "var(--bad)", fontWeight: 700 }}>
                    {pkg.cba_legal ? "✓" : "✗"}
                  </span>
                </span>
                <span style={{ flex: 1 }}>
                  {pkg.assets.map((a) => a.name).join("  +  ")}
                  <div className="meta" style={{ fontSize: "0.7rem" }}>
                    out {fmtM(pkg.salary_out)} → in {fmtM(pkg.salary_in)} (max {fmtM(pkg.max_salary_in)})
                  </div>
                </span>
                <span style={{ width: 90, textAlign: "right" }}>
                  <div style={{ fontWeight: 700 }}>{pkg.package_tvs.toFixed(1)}</div>
                  <div className="meta" style={{ fontSize: "0.7rem" }}>gap {pkg.gap_pct}%</div>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
