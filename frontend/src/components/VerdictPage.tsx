import type { Finding, MinExperiment } from "../types";
import { PERSONAS } from "../types";
import { SevBadge } from "./SevBadge";
import "./VerdictPage.css";

/** Full-page verdict report — replaces the old bottom slide-up modal.
 *  This is a printable academic-panel report: masthead, ranked findings on
 *  left, minimum experiment + consensus on right. Agent IDs link back to the
 *  trace view. */
export function VerdictPage({
  verdict,
  paperTitle,
  sessionId,
  selected,
  onSelect,
  onCopyYaml,
  onBackToTrace,
}: {
  verdict: { ranked: Finding[]; minExperiment: MinExperiment | null };
  paperTitle: string;
  sessionId: string | null;
  selected: string | null;
  onSelect: (id: string | null) => void;
  onCopyYaml: (yaml: string) => void;
  onBackToTrace: () => void;
}) {
  const exp = verdict.minExperiment;
  return (
    <div className="verdict-page">
      <header className="verdict-page-head">
        <div>
          <div className="j-mono j-sc j-dim">verdict report · session {sessionId?.slice(0, 6) ?? "—"}</div>
          <div className="verdict-page-title j-serif">{paperTitle || "Ranked concerns"}</div>
        </div>
        <div className="verdict-page-stamp-row">
          <div className="j-mono j-sc stamp">quorum reached</div>
          <button className="btn j-mono j-sc" onClick={onBackToTrace}>← back to trace</button>
        </div>
      </header>

      <div className="verdict-page-body">
        <section className="verdict-left">
          <div className="verdict-section-label j-mono j-sc j-dim">ranked concerns</div>
          {verdict.ranked.map((f) => {
            const persona = PERSONAS.find((p) => p.id === f.id.split("-")[0]);
            const seat = persona?.seat ?? "a";
            return (
              <article
                key={f.id}
                className={`finding-row ${selected === f.id ? "finding-selected" : ""}`}
                style={{ ["--seat" as string]: `var(--seat-${seat})` }}
              >
                <div className="finding-rank j-serif">{String(f.rank).padStart(2, "0")}</div>
                <div className="finding-body">
                  <div className="finding-head">
                    <SevBadge sev={f.sev} />
                    <span className="j-mono j-sc j-dim">surfaced by</span>
                    <button
                      className="finding-agent-id j-mono"
                      onClick={() => onSelect(selected === f.id ? null : f.id)}
                      aria-pressed={selected === f.id}
                    >
                      {f.id}
                    </button>
                    <span className="j-mono j-tiny j-dim">· {f.section}</span>
                    {f.cites.length > 0 && (
                      <span className="j-mono j-tiny j-dim">· cites: {f.cites.join(", ")}</span>
                    )}
                  </div>
                  <div className="finding-title j-serif">{f.title}</div>
                  <div className="finding-text j-serif">{f.text}</div>
                </div>
              </article>
            );
          })}
        </section>

        <aside className="verdict-right">
          {exp && (
            <div className="minexp-card">
              <div className="j-mono j-sc j-dim">minimum experiment</div>
              <div className="minexp-title j-serif">{exp.title}</div>
              <hr className="j-rule-d" />
              <div className="j-mono j-tiny j-dim">resolves</div>
              <div className="minexp-resolves">
                {exp.resolves.map((r) => (
                  <span key={r} className="pill minexp-pill j-mono">{r}</span>
                ))}
              </div>
              <div className="j-mono j-tiny j-dim minexp-cost-label">estimated cost</div>
              <div className="minexp-cost j-mono">
                {exp.cost.gpu_hours} {exp.cost.gpu_type}-hours · {exp.cost.eval_sweeps} eval sweeps
              </div>
              <button
                className="btn btn-primary j-mono j-sc minexp-copy"
                onClick={() => onCopyYaml(exp.yaml)}
              >
                copy as experiment.yaml
              </button>
              <details className="minexp-yaml-details">
                <summary className="j-mono j-tiny j-dim">preview yaml</summary>
                <pre className="minexp-yaml-preview j-mono">{exp.yaml}</pre>
              </details>
            </div>
          )}
          <div className="consensus">
            <div className="j-mono j-sc j-dim">consensus</div>
            <div className="consensus-text j-serif">
              {verdict.ranked.filter((f) => f.sev !== "note").length} of {verdict.ranked.length}{" "}
              reviewers find material concerns. Steelman proposes a minimal rewrite.
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
