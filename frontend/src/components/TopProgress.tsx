import type { Phase, TraceEvent } from "../types";
import "./TopProgress.css";

const ORDER: Phase[] = ["idle", "intake", "reading", "deliberation", "converging", "verdict"];

export function TopProgress({
  phase,
  verdictReady,
  verdictTraces,
}: {
  phase: Phase;
  verdictReady: boolean;
  verdictTraces: TraceEvent[];
}) {
  const idx = ORDER.indexOf(phase);
  const total = ORDER.length - 1; // drop idle from denominator
  const pct = phase === "idle" ? 0 : Math.max(0, ((idx - 0) / total) * 100);
  const composing = phase === "verdict" && !verdictReady;
  const lastTrace = verdictTraces[verdictTraces.length - 1];

  return (
    <div className="topprog" aria-label="session progress">
      <div className="topprog-bar">
        <div className="topprog-fill" style={{ width: `${pct}%` }} />
        {composing && <div className="topprog-pulse" aria-hidden="true" />}
      </div>
      {composing && (
        <div className="topprog-compose j-mono">
          <span className="j-sc j-dim topprog-compose-label">composing verdict</span>
          {lastTrace ? (
            <span className="topprog-compose-text">
              {lastTrace.text}
              <span className="j-caret" />
            </span>
          ) : (
            <span className="topprog-compose-text j-dim">spinning up…</span>
          )}
        </div>
      )}
    </div>
  );
}
