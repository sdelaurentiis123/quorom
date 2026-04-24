import type { TraceEvent } from "../types";
import "./ChairCard.css";

const ICON: Record<string, string> = {
  tool: "$",
  flag: "!",
  commit: "✓",
  think: "›",
  read: "›",
};

export function ChairCard({ traces, live }: { traces: TraceEvent[]; live: boolean }) {
  const last = traces.slice(-6);
  return (
    <article className={`chair-card ${live ? "chair-live" : ""}`}>
      <header className="chair-head">
        <span className="chair-id j-mono j-sc">CHAIR</span>
        <span className="chair-name j-serif">The Chair</span>
        <span className={`pill chair-pill ${live ? "chair-pill-live" : ""}`}>
          {live ? "reading" : "standing by"}
        </span>
      </header>
      <div className="chair-angle j-serif j-dim">Synthesizes and rules. Identifies attack vectors.</div>

      <div className="chair-log" role="log" aria-live="polite">
        {last.length === 0 && (
          <div className="log-queued j-mono j-dim j-tiny">
            queued… paper will arrive shortly
          </div>
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
