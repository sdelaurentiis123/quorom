import { useMemo } from "react";
import type { Finding, Paper, PersonaId, Phase, RecommendedExperiment, TraceEvent } from "../types";
import { ClaudeCodePackage } from "./ClaudeCodePackage";
import { ChatCard } from "./ChatCard";
import "./VerdictPage.css";

type Verdict = {
  ranked: Finding[];
  recommendedExperiment: RecommendedExperiment | null;
  reportMarkdown: string;
};

export function VerdictPage({
  verdict,
  verdictTraces,
  phase,
  paper,
  sessionId,
  selected,
  committedAgentIds,
  onSelect,
  onBackToTrace,
}: {
  verdict: Verdict | null;
  verdictTraces: TraceEvent[];
  phase: Phase;
  paper: Paper | null;
  sessionId: string | null;
  selected: string | null;
  committedAgentIds: PersonaId[];
  onSelect: (id: string | null) => void;
  onBackToTrace: () => void;
}) {
  const composing = verdict === null;
  const markdown = useMemo(
    () => (verdict ? buildClaudeCodeMarkdown(paper, verdict) : ""),
    [paper, verdict],
  );
  const lastTrace = verdictTraces[verdictTraces.length - 1];
  const recentTraces = verdictTraces.slice(-6);

  return (
    <div className="verdict-page">
      <header className="verdict-page-head">
        <div>
          <div className="j-mono j-sc j-dim">
            verdict report · session {sessionId?.slice(0, 6) ?? "—"}
          </div>
          <div className="verdict-page-title j-serif">
            {paper?.title || "Ranked concerns"}
          </div>
        </div>
        <div className="verdict-page-stamp-row">
          {composing ? (
            <div className="j-mono j-sc verdict-composing-stamp">composing…</div>
          ) : (
            <div className="j-mono j-sc stamp">quorum reached</div>
          )}
          <button
            className="btn j-mono j-sc"
            onClick={onBackToTrace}
            disabled={phase !== "verdict"}
          >
            ← back to trace
          </button>
        </div>
      </header>

      <div className="verdict-page-body">
        <section className="verdict-left">
          {composing ? (
            <div className="verdict-composing-panel">
              <div className="shim verdict-pdf-skeleton" />
              <div className="verdict-composing-caption j-mono j-dim">
                writing the review panel's report…
              </div>
              <div className="verdict-composing-log j-mono">
                {recentTraces.length === 0 && (
                  <div className="j-dim j-tiny">
                    {phase === "verdict"
                      ? "spinning up prose composer…"
                      : "reviewers still deliberating…"}
                  </div>
                )}
                {recentTraces.map((t, i) => (
                  <div key={i} className="verdict-composing-line">
                    <span className="j-dim">›</span> {t.text}
                    {i === recentTraces.length - 1 && <span className="j-caret" />}
                  </div>
                ))}
              </div>
              {lastTrace && (
                <div className="verdict-composing-progress-label j-mono j-sc j-dim">
                  {verdictTraces.length} trace line{verdictTraces.length === 1 ? "" : "s"} so far
                </div>
              )}
            </div>
          ) : (
            <iframe
              title="verdict PDF"
              src={`/api/sessions/${sessionId}/verdict.pdf#view=FitH&navpanes=0&toolbar=1`}
              className="verdict-pdf-frame"
            />
          )}
          <div className="verdict-left-foot">
            {!composing && (
              <a
                className="btn-ghost j-mono j-sc"
                href={`/api/sessions/${sessionId}/verdict.pdf`}
                download={`quorum-verdict-${sessionId}.pdf`}
              >
                ↓ download pdf
              </a>
            )}
          </div>
        </section>

        <aside className="verdict-right">
          {composing ? (
            <>
              <div className="verdict-right-placeholder shim" />
              <div className="verdict-right-placeholder shim" style={{ minHeight: 240 }} />
            </>
          ) : (
            <>
              <ClaudeCodePackage
                markdown={markdown}
                ranked={verdict!.ranked}
                selected={selected}
                onSelect={onSelect}
                recommendedExperiment={verdict!.recommendedExperiment}
              />
              <ChatCard
                sessionId={sessionId}
                committedAgentIds={committedAgentIds}
              />
            </>
          )}
        </aside>
      </div>
    </div>
  );
}

function buildClaudeCodeMarkdown(paper: Paper | null, verdict: Verdict): string {
  const title = paper?.title || "(untitled paper)";
  const paperId = paper?.id ? `arXiv:${paper.id}` : "uploaded PDF";
  const ranked = verdict.ranked.slice(0, 5);
  const exp = verdict.recommendedExperiment;

  const concerns = ranked
    .map((f) => {
      const agent = f.id.split("-")[0];
      const sev = (f.sev || "note").toUpperCase();
      // Defensive: reviewers sometimes return cites as a string, null, or omit
      // it entirely. Normalize to an array of strings before we touch it.
      const citesArr = Array.isArray(f.cites)
        ? f.cites
        : typeof f.cites === "string" && f.cites
        ? [f.cites as unknown as string]
        : [];
      const citesLine = citesArr.length ? `> Cites: ${citesArr.join(", ")}` : "";
      return [
        `### ${String(f.rank).padStart(2, "0")}. [${sev}] ${f.title}`,
        ``,
        `_Surfaced by ${agent} · ${f.section}_`,
        citesLine,
        ``,
        f.text,
      ]
        .filter((l) => l !== "")
        .join("\n");
    })
    .join("\n\n");

  const expBlock = exp
    ? [
        `## Recommended next experiment`,
        ``,
        `**${exp.title}**`,
        ``,
        exp.prose,
        Array.isArray(exp.resolves) && exp.resolves.length
          ? `\n_Resolves: ${exp.resolves.join(", ")}_`
          : "",
      ]
        .filter((l) => l !== "")
        .join("\n")
    : "";

  return [
    `# Revisions for ${title}`,
    ``,
    `> Source: ${paperId}`,
    `> Reviewed by the Quorum adversarial panel. ${ranked.length} concern(s) surfaced.`,
    ``,
    `## Top concerns`,
    ``,
    concerns,
    ``,
    expBlock,
    ``,
    `---`,
    ``,
    `**Please address each concern above in order of rank. Cite the specific section / figure / equation each change targets. Consider running the recommended next experiment to resolve the highest-priority concerns.**`,
    ``,
  ].join("\n");
}
