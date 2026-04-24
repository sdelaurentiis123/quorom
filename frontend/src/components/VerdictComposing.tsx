import type { TraceEvent } from "../types";
import "./VerdictComposing.css";

/** Shown during the brief window between phase→"verdict" and verdict.ready.
 *  Keeps the user visually informed while the final LLM composes ranked
 *  findings + min-experiment YAML. */
export function VerdictComposing({ traces }: { traces: TraceEvent[] }) {
  const last = traces.slice(-8);
  return (
    <div className="verdict-composing">
      <div className="verdict-composing-inner">
        <div className="j-mono j-sc j-dim">composing verdict…</div>
        <div className="j-serif verdict-composing-title">
          Ranking findings and drafting minimum experiment
        </div>
        <div className="verdict-composing-log">
          {last.map((t, i) => (
            <div key={i} className="log-line j-mono">
              <span className="log-icon j-dim">›</span>
              <span className="log-text">{t.text}</span>
              {i === last.length - 1 && <span className="j-caret" />}
            </div>
          ))}
          {last.length === 0 && (
            <div className="j-mono j-dim j-tiny">spinning up…</div>
          )}
        </div>
      </div>
    </div>
  );
}
