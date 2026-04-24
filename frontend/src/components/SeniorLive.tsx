import type { SeniorId, SessionState } from "../types";
import { SENIORS } from "../types";
import "./SeniorLive.css";

const ICON: Record<string, string> = {
  tool: "$",
  flag: "!",
  commit: "✓",
  think: "›",
  read: "›",
};

export function SeniorLive({
  sid,
  slice,
}: {
  sid: SeniorId;
  slice: SessionState["senior"][SeniorId];
}) {
  const senior = SENIORS.find((s) => s.id === sid)!;
  const s = slice ?? { state: "queued" as const, progress: 0, traces: [] };
  const last = s.traces.slice(-5);
  const live = s.state === "reviewing";
  const done = s.state === "signed";
  const inconc = s.state === "inconclusive";

  return (
    <article className={`senior-live ${live ? "senior-live-thinking" : ""} ${done ? "senior-live-done" : ""} ${inconc ? "senior-live-inconc" : ""}`}>
      <header className="senior-live-head">
        <div>
          <span className="j-mono j-sc senior-live-id">senior · {sid.toLowerCase()}</span>
          <span className="j-serif senior-live-name">{senior.name}</span>
        </div>
        <span className={`pill senior-live-pill pill-${s.state}`}>{s.state}</span>
      </header>
      <div className="senior-live-angle j-serif j-dim">{senior.angle}</div>

      <div className="senior-live-progress">
        <div className="senior-live-progress-fill" style={{ width: `${s.progress * 100}%` }} />
      </div>

      <div className="senior-live-log" role="log" aria-live="polite">
        {last.length === 0 && (
          <div className="j-mono j-dim j-tiny">queued…</div>
        )}
        {last.map((t, i) => {
          const isLast = i === last.length - 1;
          return (
            <div key={`${t.t}-${i}`} className={`log-line j-mono ${isLast && live ? "log-live" : ""}`}>
              <span className="log-icon j-dim">{ICON[t.kind] ?? "›"}</span>
              <span className="log-text">{t.text}</span>
              {isLast && live && <span className="j-caret" />}
            </div>
          );
        })}
      </div>
    </article>
  );
}
