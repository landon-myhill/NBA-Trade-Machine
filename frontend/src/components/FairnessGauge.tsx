import type { AssetValuation, CBASideCheck, FairnessReport, Team } from "../types";

function formatM(dollars: number): string {
  return `$${(dollars / 1_000_000).toFixed(1)}M`;
}

const TIER_COLOR: Record<CBASideCheck["tax_tier"], string> = {
  under_cap: "var(--good)",
  over_cap: "var(--muted)",
  luxury_tax: "var(--warn)",
  first_apron: "var(--warn)",
  second_apron: "var(--bad)",
};

function CBABlock({ check }: { check: CBASideCheck }) {
  return (
    <div
      style={{
        marginTop: "0.5rem",
        padding: "0.6rem 0.75rem",
        background: "var(--panel)",
        borderRadius: "6px",
        border: `1px solid ${check.legal ? "var(--border)" : "var(--bad)"}`,
        fontSize: "0.82rem",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.3rem" }}>
        <span>
          <span style={{ color: TIER_COLOR[check.tax_tier], fontWeight: 600 }}>
            {check.tax_tier_label}
          </span>
          <span className="meta" style={{ marginLeft: "0.5rem", fontSize: "0.75rem" }}>
            payroll {formatM(check.total_team_salary)}
          </span>
        </span>
        <span style={{ color: check.legal ? "var(--good)" : "var(--bad)", fontWeight: 600 }}>
          {check.legal ? "✓ Legal" : "✗ Illegal"}
        </span>
      </div>
      <div className="meta" style={{ fontSize: "0.75rem" }}>
        Out {formatM(check.salary_out)} → In {formatM(check.salary_in)} (max{" "}
        {formatM(check.max_salary_in)})
      </div>
      {check.warnings.map((w, i) => (
        <div key={i} style={{ color: "var(--bad)", fontSize: "0.75rem", marginTop: "0.25rem" }}>
          ⚠ {w}
        </div>
      ))}
    </div>
  );
}

interface Props {
  report: FairnessReport;
  teams: Team[];
}

const VERDICT_LABEL: Record<FairnessReport["verdict"], string> = {
  fair: "Fair",
  slightly_uneven: "Slightly uneven",
  lopsided: "Lopsided",
  very_lopsided: "Very lopsided",
};

function gaugeColor(score: number): string {
  if (score >= 90) return "var(--good)";
  if (score >= 75) return "var(--warn)";
  return "var(--bad)";
}

function SubscoreBars({ v }: { v: AssetValuation }) {
  if (!v.subscores) return null;
  const s = v.subscores;
  const rows: [string, number][] = [
    ["Production", s.production],
    ["Efficiency", s.efficiency],
    ["Impact", s.impact],
    ["Two-way", s.two_way],
  ];
  return (
    <div style={{ fontSize: "0.7rem", marginTop: "0.3rem" }}>
      {rows.map(([label, score]) => (
        <div
          key={label}
          style={{
            display: "grid",
            gridTemplateColumns: "70px 1fr 30px",
            alignItems: "center",
            gap: "0.4rem",
            marginBottom: "0.15rem",
          }}
        >
          <span className="meta">{label}</span>
          <div
            style={{
              height: "4px",
              background: "var(--panel)",
              borderRadius: "2px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${Math.min(100, Math.max(0, score))}%`,
                height: "100%",
                background:
                  score >= 75
                    ? "var(--good)"
                    : score >= 40
                      ? "var(--accent)"
                      : "var(--muted)",
              }}
            />
          </div>
          <span className="meta" style={{ textAlign: "right" }}>
            {Math.round(score)}
          </span>
        </div>
      ))}
    </div>
  );
}

function ValuationRow({ v }: { v: AssetValuation }) {
  return (
    <div className="valuation-row" style={{ alignItems: "flex-start" }}>
      <span
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.15rem",
          flex: 1,
        }}
      >
        <span>
          {v.label}
          {v.tier !== null && (
            <span className="tier-pill">
              T{v.tier} · {v.tier_label}
            </span>
          )}
        </span>
        {v.archetype && (
          <span
            className="meta"
            style={{ fontSize: "0.7rem", color: "var(--accent)" }}
          >
            {v.archetype}
          </span>
        )}
        {v.kind === "player" &&
          (v.contract_adjustment !== 0 || v.current_salary > 0) && (
            <span className="meta" style={{ fontSize: "0.75rem" }}>
              contract{" "}
              <span
                style={{
                  color:
                    v.contract_adjustment > 0
                      ? "var(--good)"
                      : v.contract_adjustment < 0
                        ? "var(--bad)"
                        : "var(--muted)",
                }}
              >
                {v.contract_adjustment > 0 ? "+" : ""}
                {v.contract_adjustment.toFixed(1)}
              </span>
            </span>
          )}
        {v.kind === "player" && <SubscoreBars v={v} />}
      </span>
      <span style={{ fontWeight: 600 }}>{v.total_value.toFixed(1)}</span>
    </div>
  );
}

export function FairnessGauge({ report, teams }: Props) {
  const teamName = (id: string) =>
    teams.find((t) => t.id === id)?.name ?? id;

  return (
    <div className="fairness-result">
      <div className="gauge">
        <div className="gauge-bar">
          <div
            className="gauge-fill"
            style={{
              width: `${report.fairness_score}%`,
              background: gaugeColor(report.fairness_score),
            }}
          />
        </div>
        <div className="gauge-score">{report.fairness_score.toFixed(1)}</div>
        <span className={`verdict ${report.verdict}`}>
          {VERDICT_LABEL[report.verdict]}
        </span>
        <span
          style={{
            padding: "0.25rem 0.6rem",
            borderRadius: "999px",
            fontSize: "0.8rem",
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            background: report.cba_legal
              ? "rgba(63,185,80,0.15)"
              : "rgba(248,81,73,0.18)",
            color: report.cba_legal ? "var(--good)" : "var(--bad)",
            marginLeft: "0.5rem",
          }}
        >
          {report.cba_legal ? "CBA Legal" : "CBA Illegal"}
        </span>
      </div>

      <div className="breakdown">
        {report.sides.map((side) => (
          <div
            key={side.team_id}
            className="panel"
            style={{ background: "var(--panel-2)" }}
          >
            <h2>{teamName(side.team_id)}</h2>

            <h3>Sending</h3>
            {side.sending.map((v, i) => (
              <ValuationRow key={i} v={v} />
            ))}
            {side.sending.length === 0 && <div className="meta">Nothing</div>}

            <h3>Receiving</h3>
            {side.receiving.map((v, i) => (
              <ValuationRow key={i} v={v} />
            ))}
            {side.receiving.length === 0 && <div className="meta">Nothing</div>}

            <div className="totals">
              <span>Net</span>
              <span className={`net ${side.net >= 0 ? "positive" : "negative"}`}>
                {side.net >= 0 ? "+" : ""}
                {side.net.toFixed(1)}
              </span>
            </div>
            {report.cba_sides
              .filter((c) => c.team_id === side.team_id)
              .map((c) => (
                <CBABlock key={c.team_id} check={c} />
              ))}
          </div>
        ))}
      </div>

      <div className="explanation">
        {report.explanation.map((line, i) => (
          <p key={i}>{line}</p>
        ))}
      </div>
    </div>
  );
}
