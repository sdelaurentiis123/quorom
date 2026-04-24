import { useEffect, useState } from "react";
import type { Finding, MinExperiment } from "../types";
import { PERSONAS } from "../types";
import { SevBadge } from "./SevBadge";
import "./VerdictReport.css";

export function VerdictReport({
  verdict,
  selected,
  onSelect,
  onCopyYaml,
}: {
  verdict: { ranked: Finding[]; minExperiment: MinExperiment | null };
  selected: string | null;
  onSelect: (id: string | null) => void;
  onCopyYaml: (yaml: string) => void;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const t = window.setTimeout(() => setMounted(true), 30);
    return () => window.clearTimeout(t);
  }, []);

  const shrunk = selected !== null;
  const exp = verdict.minExperiment;

  return (
    <div
      className={`verdict ${mounted ? "verdict-mounted" : ""} ${shrunk ? "verdict-shrunk" : ""}`}
      role="region"
      aria-label="verdict"
    >
      <header className="verdict-head">
        <div>
          <div className="j-mono j-sc j-dim verdict-label">verdict · ranked concerns</div>
          <div className="verdict-title j-serif">{verdict.ranked.length} concerns surfaced</div>
        </div>
        <div className="j-mono j-sc j-dim stamp">quorum reached</div>
      </header>

      <div className="verdict-body">
        <div className="verdict-left">
          {verdict.ranked.map((f) => {
            const persona = PERSONAS.find((p) => p.id === f.id.split("-")[0]);
            const seat = persona?.seat ?? "a";
            return (
              <div
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
                  </div>
                  <div className="finding-title j-serif">{f.title}</div>
                  <div className="finding-text j-serif">{f.text}</div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="verdict-right">
          {exp && (
            <div className="minexp-card">
              <div className="j-mono j-sc j-dim">minimum experiment</div>
              <div className="minexp-title j-serif">{exp.title}</div>
              <hr className="j-rule-d minexp-rule" />
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
            </div>
          )}
          <div className="consensus">
            <div className="j-mono j-sc j-dim">consensus</div>
            <div className="consensus-text j-serif">
              {verdict.ranked.filter((f) => f.sev !== "note").length} of {verdict.ranked.length}{" "}
              reviewers find material concerns. Steelman dissents in favor of a rewritten claim.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
