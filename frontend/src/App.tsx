import { useState } from "react";
import Rankings from "./pages/Rankings";
import TradeFinder from "./pages/TradeFinder";
import TradeMachine from "./pages/TradeMachine";

type Tab = "trade" | "rankings" | "finder";

export default function App() {
  const [tab, setTab] = useState<Tab>("trade");
  return (
    <div className="app">
      <div className="tab-bar">
        <button className={`tab${tab === "trade" ? " active" : ""}`} onClick={() => setTab("trade")}>
          Trade Builder
        </button>
        <button className={`tab${tab === "rankings" ? " active" : ""}`} onClick={() => setTab("rankings")}>
          League Rankings
        </button>
        <button className={`tab${tab === "finder" ? " active" : ""}`} onClick={() => setTab("finder")}>
          Trade Finder
        </button>
      </div>
      {tab === "trade" && <TradeMachine />}
      {tab === "rankings" && <Rankings />}
      {tab === "finder" && <TradeFinder />}
    </div>
  );
}
