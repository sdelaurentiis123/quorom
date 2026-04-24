import type { AgentSlice, Persona } from "../types";
import { SevBadge } from "./SevBadge";
import "./AgentCard.css";

const ICON: Record<string, string> = {
  tool: "$",
  flag: "!",
  commit: "✓",
  think: "›",
  read: "›",
};

export function AgentCard({
  persona,
  slice,
  onSelect,
}: {
  persona: Persona;
  slice: AgentSlice | undefined;
  onSelect?: (id: string) => void;
}) {
  const s = slice ?? { state: "queued" as const, traces: [], progress: 0, finding: null };
  const last3 = s.traces.slice(-3);

  return (
    <article
      role="button"
      aria-label={`${persona.name} (${persona.id}) — ${s.state}`}
      tabIndex={0}
      onClick={() => onSelect?.(persona.id)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSelect?.(persona.id); }}
      className={`agent-card seat-${persona.seat} ${s.state === "reading" ? "thinking" : ""}`}
      style={{ ["--seat" as string]: `var(--seat-${persona.seat})` }}
    >
      <header className="agent-head">
        <div>
          <span className="agent-id j-mono j-sc">{persona.id}</span>
          <span className="agent-name j-serif">{persona.name}</span>
        </div>
        <span className={`pill pill-${s.state}`}>{s.state}</span>
      </header>

      <div className="agent-angle j-serif j-dim">{persona.angle}</div>

      <div className="agent-log" role="log" aria-live="polite">
        {last3.length === 0 && s.state === "queued" && (
          <div className="log-queued j-mono j-dim j-tiny">queued…</div>
        )}
        {last3.map((t, i) => {
          const isLast = i === last3.length - 1;
          return (
            <div
              key={`${t.t}-${i}`}
              className={`log-line j-mono ${isLast && s.state === "reading" ? "log-live" : ""}`}
            >
              <span className="log-icon j-dim">{ICON[t.kind] ?? "›"}</span>
              <span className="log-text">{t.text}</span>
              {isLast && s.state === "reading" && <span className="j-caret" />}
            </div>
          );
        })}
      </div>

      {s.state === "done" && s.finding && (
        <footer className="agent-finding">
          <SevBadge sev={s.finding.sev} />
          <div className="agent-finding-text">{s.finding.text}</div>
        </footer>
      )}
    </article>
  );
}
