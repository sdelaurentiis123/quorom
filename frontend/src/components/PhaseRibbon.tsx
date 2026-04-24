import type { Phase } from "../types";
import "./PhaseRibbon.css";

const PHASES: { key: Phase; label: string }[] = [
  { key: "intake", label: "01 Intake" },
  { key: "reading", label: "02 Reading" },
  { key: "deliberation", label: "03 Deliberation" },
  { key: "converging", label: "04 Converging" },
  { key: "verdict", label: "05 Verdict" },
];

const ORDER: Phase[] = ["idle", "intake", "reading", "deliberation", "converging", "verdict"];

export function PhaseRibbon({ phase }: { phase: Phase }) {
  const activeIdx = ORDER.indexOf(phase);
  return (
    <div className="phase-ribbon" role="navigation" aria-label="session phases">
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
  );
}
