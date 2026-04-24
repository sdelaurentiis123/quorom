import { SENIORS, type SeniorId, type SessionState } from "../types";
import "./ConvergingBar.css";

export function ConvergingBar({ senior }: { senior: SessionState["senior"] }) {
  return (
    <div className="converging-bar" aria-label="senior review">
      {SENIORS.map((s) => {
        const slice = senior[s.id as SeniorId] ?? { state: "queued" as const, progress: 0 };
        const done = slice.state === "signed";
        return (
          <div key={s.id} className="senior-card">
            <header className="senior-head">
              <span className="j-mono j-sc senior-id">senior · {s.id.toLowerCase()}</span>
              <span className={`pill senior-pill ${done ? "senior-pill-done" : ""}`}>
                {done ? "signed" : slice.state === "reviewing" ? "reviewing" : "queued"}
              </span>
            </header>
            <div className="senior-name j-serif">{s.name}</div>
            <div className="senior-angle j-serif j-dim">{s.angle}</div>
            <div className="senior-progress" role="progressbar" aria-valuemin={0} aria-valuemax={1} aria-valuenow={slice.progress}>
              <div className="senior-progress-fill" style={{ width: `${slice.progress * 100}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
