import { useEffect, useState } from "react";
import { api } from "../api/client";
import { FairnessGauge } from "../components/FairnessGauge";
import { TeamPanel } from "../components/TeamPanel";
import type { FairnessReport, Team, TradeAsset } from "../types";

function sameAsset(a: TradeAsset, b: TradeAsset): boolean {
  if (a.player_id && b.player_id) return a.player_id === b.player_id;
  if (a.pick_id && b.pick_id) return a.pick_id === b.pick_id;
  return false;
}

export default function TradeMachine() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [teamA, setTeamA] = useState<string | null>(null);
  const [teamB, setTeamB] = useState<string | null>(null);
  const [sendingA, setSendingA] = useState<TradeAsset[]>([]);
  const [sendingB, setSendingB] = useState<TradeAsset[]>([]);
  const [report, setReport] = useState<FairnessReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listTeams().then(setTeams).catch((e) => setError(e.message));
  }, []);

  const toggleA = (asset: TradeAsset) => {
    setSendingA((s) =>
      s.some((a) => sameAsset(a, asset))
        ? s.filter((a) => !sameAsset(a, asset))
        : [...s, asset]
    );
    setReport(null);
  };

  const toggleB = (asset: TradeAsset) => {
    setSendingB((s) =>
      s.some((a) => sameAsset(a, asset))
        ? s.filter((a) => !sameAsset(a, asset))
        : [...s, asset]
    );
    setReport(null);
  };

  const onTeamAChange = (id: string) => {
    setTeamA(id);
    setSendingA([]);
    setReport(null);
  };
  const onTeamBChange = (id: string) => {
    setTeamB(id);
    setSendingB([]);
    setReport(null);
  };

  const canEvaluate =
    teamA &&
    teamB &&
    teamA !== teamB &&
    sendingA.length > 0 &&
    sendingB.length > 0;

  const evaluateTrade = async () => {
    if (!canEvaluate || !teamA || !teamB) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.evaluate([
        { team_id: teamA, sending: sendingA },
        { team_id: teamB, sending: sendingB },
      ]);
      setReport(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setSendingA([]);
    setSendingB([]);
    setReport(null);
  };

  return (
    <div className="app">
      <h1>NBA Trade Machine</h1>
      <p className="subtitle">
        Pick two teams, click assets to add them to the trade, and see how fair the deal is.
      </p>

      <div className="trade-grid">
        <TeamPanel
          teams={teams}
          selectedTeamId={teamA}
          onTeamChange={onTeamAChange}
          sending={sendingA}
          onToggleAsset={toggleA}
          excludeTeamId={teamB}
        />
        <TeamPanel
          teams={teams}
          selectedTeamId={teamB}
          onTeamChange={onTeamBChange}
          sending={sendingB}
          onToggleAsset={toggleB}
          excludeTeamId={teamA}
        />
      </div>

      <div className="evaluate-bar">
        <button onClick={evaluateTrade} disabled={!canEvaluate || loading}>
          {loading ? "Evaluating…" : "Evaluate Trade"}
        </button>
        <button
          className="ghost"
          onClick={reset}
          style={{ marginLeft: "0.75rem" }}
          disabled={sendingA.length + sendingB.length === 0}
        >
          Clear
        </button>
      </div>

      {error && <div className="error">{error}</div>}
      {report && <FairnessGauge report={report} teams={teams} />}
    </div>
  );
}
