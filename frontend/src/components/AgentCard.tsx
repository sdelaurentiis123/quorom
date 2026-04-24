import { useEffect, useRef, useState } from "react";
import type { AgentSlice, Persona, TraceEvent } from "../types";
import { SevBadge } from "./SevBadge";
import "./AgentCard.css";

const ICON: Record<string, string> = {
  tool: "$",
  flag: "!",
  commit: "✓",
  think: "›",
  read: "›",
};

const CODE_PREVIEW_LINES = 6;

/**
 * A single trace line. When the trace is a tool call whose `text` contains
 * embedded newlines, we render it as a compact code block with a "show more"
 * toggle — 6 lines visible by default, click to expand to the full snippet.
 */
function TraceLine({
  trace,
  live,
  stopCaret,
}: {
  trace: TraceEvent;
  live: boolean;
  stopCaret: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const icon = ICON[trace.kind] ?? "›";
  const hasNewline = trace.text.includes("\n");

  // Tool traces with embedded newlines: render as header + code block.
  if (hasNewline && trace.kind === "tool") {
    const [header, ...codeLines] = trace.text.split("\n");
    const total = codeLines.length;
    const overflow = total > CODE_PREVIEW_LINES;
    const visible = expanded || !overflow ? codeLines : codeLines.slice(0, CODE_PREVIEW_LINES);
    return (
      <div className={`log-line log-line-block j-mono ${live ? "log-live" : ""}`}>
        <div className="log-line-row">
          <span className="log-icon j-dim">{icon}</span>
          <span className="log-text">{header}</span>
          {live && !stopCaret && <span className="j-caret" />}
        </div>
        <pre className="log-code">{visible.join("\n")}</pre>
        {overflow && (
          <button
            type="button"
            className="log-expand j-mono j-sc j-dim"
            onClick={(e) => { e.stopPropagation(); setExpanded((x) => !x); }}
          >
            {expanded
              ? `hide (${total - CODE_PREVIEW_LINES} line${total - CODE_PREVIEW_LINES === 1 ? "" : "s"})`
              : `show ${total - CODE_PREVIEW_LINES} more line${total - CODE_PREVIEW_LINES === 1 ? "" : "s"} ↓`}
          </button>
        )}
      </div>
    );
  }

  // Single-line trace.
  return (
    <div className={`log-line j-mono ${live ? "log-live" : ""}`}>
      <span className="log-icon j-dim">{icon}</span>
      <span className="log-text">{trace.text}</span>
      {live && !stopCaret && <span className="j-caret" />}
    </div>
  );
}

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
  const logRef = useRef<HTMLDivElement>(null);
  const traceCount = s.traces.length;
  // Autoscroll as new traces stream in.
  useEffect(() => {
    if (!logRef.current) return;
    logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [traceCount, s.state]);

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

      <div className="agent-log" role="log" aria-live="polite" ref={logRef}>
        {s.traces.length === 0 && s.state === "queued" && (
          <div className="log-queued j-mono j-dim j-tiny">queued…</div>
        )}
        {s.traces.map((t, i) => {
          const isLast = i === s.traces.length - 1;
          return (
            <TraceLine
              key={`${t.t}-${i}`}
              trace={t}
              live={isLast && s.state === "reading"}
              stopCaret={false}
            />
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
