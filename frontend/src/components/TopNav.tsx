import type { Phase } from "../types";
import "./TopNav.css";

const PHASES: { key: Phase; label: string }[] = [
  { key: "intake",        label: "01 Intake" },
  { key: "reading",       label: "02 Reading" },
  { key: "deliberation",  label: "03 Deliberation" },
  { key: "converging",    label: "04 Converging" },
  { key: "verdict",       label: "05 Verdict" },
];
const ORDER: Phase[] = ["idle", "intake", "reading", "deliberation", "converging", "verdict"];

export function TopNav({
  phase,
  activeTab,
  verdictReady,
  onSetTab,
}: {
  phase: Phase;
  activeTab: "trace" | "verdict";
  verdictReady: boolean;
  onSetTab: (tab: "trace" | "verdict") => void;
}) {
  const activeIdx = ORDER.indexOf(phase);
  return (
    <nav className="topnav" aria-label="session navigation">
      <div className="topnav-tabs">
        <button
          className={`tab ${activeTab === "trace" ? "tab-active" : ""}`}
          onClick={() => onSetTab("trace")}
          aria-pressed={activeTab === "trace"}
        >
          <span className="j-mono j-sc tab-mono">trace</span>
        </button>
        <button
          className={`tab ${activeTab === "verdict" ? "tab-active" : ""}`}
          onClick={() => onSetTab("verdict")}
          disabled={!verdictReady}
          aria-pressed={activeTab === "verdict"}
          aria-disabled={!verdictReady}
        >
          <span className="j-mono j-sc tab-mono">verdict</span>
          {verdictReady && <span className="tab-indicator" />}
        </button>
      </div>
      <div className="topnav-ribbon">
        {PHASES.map(({ key, label }) => {
          const idx = ORDER.indexOf(key);
          const state = idx < activeIdx ? "past" : idx === activeIdx ? "active" : "future";
          return (
            <div
              key={key}
              className={`ribbon-tab ribbon-${state} j-mono j-sc`}
              aria-current={state === "active" ? "step" : undefined}
            >
              {label}
            </div>
          );
        })}
      </div>
    </nav>
  );
}
