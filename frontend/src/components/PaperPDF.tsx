import { useState } from "react";
import type { Paper } from "../types";
import "./PaperPDF.css";

/** Renders the source PDF via Chrome's native PDF viewer (`<iframe>`).
 *  Falls back to the markdown body or a download link if has_pdf is false.
 *  Includes a `View as text` toggle for accessibility. */
export function PaperPDF({
  paper,
  sessionId,
}: {
  paper: Paper | null;
  sessionId: string | null;
}) {
  const [mode, setMode] = useState<"pdf" | "text">("pdf");

  if (!paper || !sessionId) {
    return (
      <div className="paper-pdf-wrap">
        <div className="j-mono j-sc j-dim paper-pdf-label">manuscript under review</div>
        <div className="paper-pdf-loading shim" />
      </div>
    );
  }

  const hasPdf = !!paper.has_pdf;

  return (
    <div className="paper-pdf-wrap">
      <header className="paper-pdf-head">
        <div className="paper-pdf-meta">
          <div className="j-mono j-sc j-dim paper-pdf-label">manuscript under review</div>
          <div className="paper-pdf-title j-serif">{paper.title}</div>
          <div className="paper-pdf-authors j-dim j-serif">
            {paper.authors}
            {paper.id && (
              <>
                {" · "}
                <span className="j-mono paper-pdf-id">arXiv:{paper.id}</span>
              </>
            )}
          </div>
        </div>
        <div className="paper-pdf-controls">
          {hasPdf && (
            <>
              <button
                className={`btn-ghost j-mono j-sc ${mode === "pdf" ? "is-active" : ""}`}
                onClick={() => setMode("pdf")}
              >
                pdf
              </button>
              <button
                className={`btn-ghost j-mono j-sc ${mode === "text" ? "is-active" : ""}`}
                onClick={() => setMode("text")}
              >
                text
              </button>
              <a
                className="btn-ghost j-mono j-sc"
                href={`/api/sessions/${sessionId}/paper.pdf`}
                download={`paper-${paper.id || sessionId}.pdf`}
              >
                ↓
              </a>
            </>
          )}
        </div>
      </header>

      {hasPdf && mode === "pdf" ? (
        <iframe
          title="paper PDF"
          src={`/api/sessions/${sessionId}/paper.pdf#view=FitH&navpanes=0`}
          className="paper-pdf-frame"
        />
      ) : (
        <div className="paper-pdf-text">
          {paper.abstract && (
            <>
              <div className="j-mono j-sc j-dim paper-pdf-section">abstract</div>
              <p className="j-serif paper-pdf-p">{paper.abstract}</p>
            </>
          )}
          {paper.body ? (
            <pre className="paper-pdf-body-text j-serif">{paper.body}</pre>
          ) : (
            <div className="j-dim paper-pdf-loading-text">body text pending…</div>
          )}
        </div>
      )}
    </div>
  );
}
