import { useState } from "react";
import { Masthead } from "./Masthead";
import { PERSONAS } from "../types";
import "./PhaseIdle.css";

type ConvenePayload =
  | { kind: "arxiv"; id: string }
  | { kind: "pdf"; upload_id: string }
  | { kind: "demo" };

export function PhaseIdle({ onConvene }: { onConvene: (p: ConvenePayload) => void }) {
  const [url, setUrl] = useState("");
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const parseArxivId = (s: string): string | null => {
    const trimmed = s.trim();
    if (!trimmed) return null;
    const m = trimmed.match(/(\d{4}\.\d{4,5})(v\d+)?$/);
    if (m) return m[1];
    return trimmed; // permissive — backend validates
  };

  const handleConvene = () => {
    const id = parseArxivId(url);
    if (!id) {
      onConvene({ kind: "demo" });
      return;
    }
    onConvene({ kind: "arxiv", id });
  };

  const handleFile = async (file: File) => {
    if (file.type !== "application/pdf") {
      alert("PDF only");
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const resp = await fetch("/api/uploads", { method: "POST", body: form });
      if (!resp.ok) throw new Error(await resp.text());
      const data = (await resp.json()) as { upload_id: string };
      onConvene({ kind: "pdf", upload_id: data.upload_id });
    } catch (e) {
      alert(`upload failed: ${e}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="phase-idle">
      <Masthead sessionId={null} phase="idle" />
      <div className="phase-idle-body">
        <div className="phase-idle-inner">
          <div className="phase-idle-blurb j-serif">
            A panel of six reviewers will read your paper, work in parallel,
            <br />
            and return a ranked verdict with the minimum experiment to resolve the top concern.
          </div>

          <div
            className={`dropzone ${dragOver ? "dropzone-over" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const f = e.dataTransfer.files[0];
              if (f) void handleFile(f);
            }}
          >
            <div className="j-mono j-sc j-dim dz-label">drop paper here</div>
            <div className="dz-main j-serif">PDF, arXiv URL, or DOI</div>
            <div className="dz-row">
              <input
                className="j-mono dz-input"
                placeholder="arxiv.org/abs/2604.01188"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleConvene(); }}
              />
              <button className="btn btn-primary j-mono j-sc" onClick={handleConvene} disabled={uploading}>
                convene →
              </button>
            </div>
            <div className="dz-hint j-mono j-tiny j-dim">
              no URL? <button className="linklike j-mono j-tiny" onClick={() => onConvene({ kind: "demo" })}>try the demo paper</button>
            </div>
          </div>

          <div className="seat-row">
            {PERSONAS.map((p) => (
              <div key={p.id} className="seat-dot-wrap" style={{ ["--seat" as string]: `var(--seat-${p.seat})` }}>
                <span className="seat-dot" />
                <div className="seat-label j-mono j-tiny j-dim">{p.id}</div>
              </div>
            ))}
          </div>
          <div className="seat-caption j-mono j-tiny j-dim">six reviewers standing by</div>
        </div>
      </div>
    </div>
  );
}
