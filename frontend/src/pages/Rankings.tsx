import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { PlayerDetail } from "../components/PlayerDetail";
import type { RankedPlayer } from "../types";

function formatSalary(dollars: number): string {
  if (!dollars) return "—";
  const m = dollars / 1_000_000;
  return m >= 10 ? `$${m.toFixed(0)}M` : `$${m.toFixed(1)}M`;
}

const TIER_COLOR: Record<number, string> = {
  1: "#9d4edd",
  2: "#5e60ce",
  3: "#4ea8de",
  4: "#56cfe1",
  5: "#80ed99",
  6: "#a3a3a3",
  7: "#6b6b6b",
};

export default function Rankings() {
  const [players, setPlayers] = useState<RankedPlayer[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    api.rankedPlayers().then(setPlayers).catch((e) => setError(e.message));
  }, []);

  const matches = useMemo(() => {
    if (!query.trim()) return [];
    const q = query.toLowerCase();
    return players.filter((p) => p.name.toLowerCase().includes(q)).slice(0, 8);
  }, [query, players]);

  const jumpTo = (id: string) => {
    const el = rowRefs.current[id];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("ranking-flash");
      setTimeout(() => el.classList.remove("ranking-flash"), 1500);
    }
  };

  if (error) return <div className="error">{error}</div>;

  return (
    <div className="rankings">
      <div className="rankings-header">
        <h2 style={{ margin: 0 }}>League Rankings ({players.length})</h2>
        <div className="search-wrap">
          <input
            className="search-input"
            type="text"
            placeholder="Search a player to jump…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && matches.length > 0) {
                jumpTo(matches[0].id);
                setQuery("");
              }
            }}
          />
          {matches.length > 0 && (
            <div className="search-results">
              {matches.map((p) => (
                <div
                  key={p.id}
                  className="search-result"
                  onClick={() => {
                    jumpTo(p.id);
                    setQuery("");
                  }}
                >
                  <span style={{ color: "var(--muted)", marginRight: "0.5rem" }}>
                    #{p.rank}
                  </span>
                  <strong>{p.name}</strong>
                  <span style={{ marginLeft: "0.5rem", color: "var(--muted)" }}>
                    {p.team_id} · {p.position}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div ref={listRef} className="ranking-list">
        <div className="ranking-row ranking-header-row">
          <span style={{ width: 50 }}>Rank</span>
          <span style={{ flex: 1 }}>Player</span>
          <span style={{ width: 50 }}>Team</span>
          <span style={{ width: 40 }}>Pos</span>
          <span style={{ width: 40 }}>Age</span>
          <span style={{ width: 60 }}>Tier</span>
          <span style={{ width: 80 }}>Salary</span>
          <span style={{ width: 50 }}>BPM</span>
          <span style={{ width: 60 }} title="Trend: recent 2yr vs 5yr">2y/5y</span>
          <span style={{ width: 70, textAlign: "right" }}>TVS</span>
        </div>
        {players.map((p) => (
          <div
            key={p.id}
            ref={(el) => {
              rowRefs.current[p.id] = el;
            }}
            className="ranking-row"
            style={{ cursor: "pointer" }}
            onClick={() => setDetailId(p.id)}
          >
            <span style={{ width: 50, color: "var(--muted)" }}>#{p.rank}</span>
            <span style={{ flex: 1, display: "flex", flexDirection: "column" }}>
              <strong>{p.name}</strong>
              {p.archetype && (
                <span
                  className="meta"
                  style={{ fontSize: "0.7rem", color: "var(--accent)" }}
                >
                  {p.archetype}
                </span>
              )}
            </span>
            <span style={{ width: 50 }}>{p.team_id}</span>
            <span style={{ width: 40 }}>{p.position}</span>
            <span style={{ width: 40 }}>{p.age}</span>
            <span style={{ width: 60 }}>
              <span
                style={{
                  display: "inline-block",
                  padding: "0.1rem 0.4rem",
                  borderRadius: "4px",
                  background: TIER_COLOR[p.tier],
                  color: "white",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                }}
              >
                T{p.tier}
              </span>
            </span>
            <span style={{ width: 80, fontSize: "0.8rem" }}>
              {formatSalary(p.current_salary)}
              {p.years_remaining > 0 && (
                <span style={{ color: "var(--muted)" }}>
                  ×{p.years_remaining}
                </span>
              )}
            </span>
            <span style={{ width: 50, fontSize: "0.85rem" }}>
              {p.bpm.toFixed(1)}
            </span>
            <span
              style={{ width: 60, fontSize: "0.75rem" }}
              title={`2yr avg: ${p.bpm_2yr.toFixed(1)} · 5yr avg: ${p.bpm_5yr.toFixed(1)} · ratio: ${p.trend_ratio.toFixed(2)}`}
            >
              <span
                style={{
                  color:
                    p.trend_ratio > 1.1
                      ? "var(--good)"
                      : p.trend_ratio < 0.85
                        ? "var(--bad)"
                        : "var(--muted)",
                  fontWeight: 600,
                  marginRight: "0.25rem",
                }}
              >
                {p.trend_ratio > 1.1 ? "↗" : p.trend_ratio < 0.85 ? "↘" : "→"}
              </span>
              <span style={{ color: "var(--muted)" }}>
                {p.bpm_2yr.toFixed(1)}/{p.bpm_5yr.toFixed(1)}
              </span>
            </span>
            <span
              style={{
                width: 70,
                textAlign: "right",
                fontWeight: 700,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {p.total_value.toFixed(1)}
            </span>
          </div>
        ))}
      </div>
      {detailId && (
        <PlayerDetail playerId={detailId} onClose={() => setDetailId(null)} />
      )}
    </div>
  );
}
