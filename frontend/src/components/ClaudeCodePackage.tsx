import { useState } from "react";
import type { Finding, PersonaId, RecommendedExperiment } from "../types";
import { PERSONAS } from "../types";
import { SevBadge } from "./SevBadge";
import "./ClaudeCodePackage.css";

export function ClaudeCodePackage({
  markdown,
  ranked,
  selected,
  recommendedExperiment,
  onSelect,
}: {
  markdown: string;
  ranked: Finding[];
  selected: string | null;
  recommendedExperiment: RecommendedExperiment | null;
  onSelect: (id: string | null) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const doCopy = async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2200);
    } catch {
      /* ignore */
    }
  };

  const download = () => {
    const blob = new Blob([markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "quorum-revisions.md";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="cc-card">
      <header className="cc-card-head">
        <div className="j-mono j-sc cc-card-label">for Claude Code</div>
        <div className="j-serif cc-card-title">Package revisions as a prompt</div>
      </header>

      <div className="cc-card-body">
        <p className="j-serif cc-card-blurb">
          A paste-ready markdown block with the panel's top concerns, the
          recommended next experiment, and a closing directive. Drop it into
          Claude Code to apply these revisions to your paper.
        </p>

        <div className="cc-card-actions">
          <button
            className={`btn btn-primary j-mono j-sc cc-copy ${copied ? "is-copied" : ""}`}
            onClick={doCopy}
          >
            {copied ? "copied ✓" : "copy for claude code"}
          </button>
          <button className="btn j-mono j-sc cc-download" onClick={download}>
            ↓ .md
          </button>
        </div>

        <button
          className="cc-toggle j-mono j-sc j-dim"
          onClick={() => setExpanded((e) => !e)}
        >
          {expanded ? "hide preview" : "show preview"}
        </button>
        {expanded && (
          <pre className="cc-preview j-mono">{markdown}</pre>
        )}

        {recommendedExperiment && (
          <div className="cc-next-exp">
            <div className="j-mono j-sc j-dim cc-next-exp-head">
              recommended next experiment
            </div>
            <div className="j-serif cc-next-exp-title">
              {recommendedExperiment.title}
            </div>
            <p className="j-serif cc-next-exp-prose">{recommendedExperiment.prose}</p>
            {recommendedExperiment.resolves.length > 0 && (
              <div className="j-mono j-tiny j-dim">
                resolves {recommendedExperiment.resolves.join(", ")}
              </div>
            )}
          </div>
        )}

        <details className="cc-agents">
          <summary className="j-mono j-sc j-dim cc-agents-head">
            per-reviewer concerns ({ranked.length})
          </summary>
          <div className="cc-agents-list">
            {ranked.map((f) => {
              const agent = f.id.split("-")[0] as PersonaId;
              const persona = PERSONAS.find((p) => p.id === agent);
              const seat = persona?.seat ?? "a";
              return (
                <article
                  key={f.id}
                  className={`cc-finding seat-${seat} ${selected === f.id ? "is-selected" : ""}`}
                  style={{ ["--seat" as string]: `var(--seat-${seat})` }}
                >
                  <div className="cc-finding-head">
                    <span className="cc-finding-rank j-serif">
                      {String(f.rank).padStart(2, "0")}
                    </span>
                    <SevBadge sev={f.sev} />
                    <button
                      className="cc-finding-id j-mono"
                      onClick={() => onSelect(selected === f.id ? null : f.id)}
                    >
                      {f.id}
                    </button>
                    <span className="j-mono j-tiny j-dim">· {f.section}</span>
                  </div>
                  <div className="cc-finding-title j-serif">{f.title}</div>
                  <div className="cc-finding-text j-serif">{f.text}</div>
                </article>
              );
            })}
          </div>
        </details>
      </div>
    </section>
  );
}
