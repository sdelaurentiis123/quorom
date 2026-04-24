import { useMemo } from "react";
import type { Paper, PersonaId } from "../types";
import "./PaperBody.css";

/** Renders the actual paper body returned by the backend. Markdown-ish
 *  text: we split into section blocks on `##` / `#` markdown headings or
 *  numbered-section headings. Inline highlights (METH/STAT/etc.) still
 *  light up as the orchestrator identifies vectors — done by substring
 *  match against the persona's `angle` phrases. */
export function PaperBody({
  paper,
  vectors,
}: {
  paper: Paper | null;
  vectors: { agent_id: PersonaId; angle: string }[];
}) {
  const blocks = useMemo(() => splitBody(paper?.body ?? ""), [paper?.body]);

  if (!paper) {
    return (
      <div className="paper-body">
        <div className="j-mono j-sc j-dim paper-label">manuscript under review</div>
        <div className="j-dim paper-loading">extracting structure…</div>
      </div>
    );
  }

  return (
    <div className="paper-body" aria-label="manuscript">
      <div className="j-mono j-sc j-dim paper-label">manuscript under review</div>
      <h1 className="paper-title j-serif">{paper.title}</h1>
      <div className="paper-authors j-dim j-serif">
        {paper.authors}
        {paper.id && (
          <>
            {" · "}
            <span className="j-mono paper-id">arXiv:{paper.id}</span>
          </>
        )}
      </div>

      <hr className="j-rule paper-rule" />

      <div className="j-mono j-sc j-dim paper-section-label">abstract</div>
      <p className="j-serif paper-p">{paper.abstract}</p>

      {paper.sections && paper.sections.length > 0 && (
        <>
          <div className="j-mono j-sc j-dim paper-section-label">sections</div>
          <div className="paper-section-index">
            {paper.sections.map((s) => (
              <div key={s.id} className="j-mono j-tiny j-dim section-index-row">
                <span className="section-id">{s.id}</span>
                <span>{s.title}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {blocks.length > 0 ? (
        <div className="paper-body-text">
          {blocks.map((b, i) => (
            <Block key={i} block={b} vectors={vectors} />
          ))}
        </div>
      ) : (
        <div className="j-dim paper-loading">body text pending…</div>
      )}
    </div>
  );
}

type BlockT = { heading: string | null; text: string };

function splitBody(body: string): BlockT[] {
  if (!body) return [];
  const lines = body.split("\n");
  const blocks: BlockT[] = [];
  let current: BlockT = { heading: null, text: "" };
  const flush = () => { if (current.heading || current.text.trim()) blocks.push(current); };

  for (const line of lines) {
    const mdH = line.match(/^(#{1,3})\s+(.{2,120})$/);
    const numH = line.match(/^(\d+(?:\.\d+)?)\s+([A-Z][\w ,:\-]{2,80})$/);
    if (mdH) {
      flush();
      current = { heading: mdH[2].trim(), text: "" };
    } else if (numH && line.trim() === line.trim()) {
      flush();
      current = { heading: `§${numH[1]} ${numH[2]}`, text: "" };
    } else {
      current.text += line + "\n";
    }
  }
  flush();

  // Trim each block; drop empties.
  return blocks
    .map((b) => ({ heading: b.heading, text: b.text.trim() }))
    .filter((b) => b.heading || b.text)
    .slice(0, 30); // cap for UI
}

function Block({ block, vectors }: { block: BlockT; vectors: { agent_id: PersonaId; angle: string }[] }) {
  return (
    <section className="paper-block">
      {block.heading && (
        <div className="j-mono j-sc j-dim paper-block-head">{block.heading}</div>
      )}
      {block.text && (
        <p className="j-serif paper-p">
          <Highlighted text={block.text} vectors={vectors} />
        </p>
      )}
    </section>
  );
}

function Highlighted({
  text,
  vectors,
}: {
  text: string;
  vectors: { agent_id: PersonaId; angle: string }[];
}) {
  // Pick a short anchor phrase from each vector angle and highlight wherever
  // it appears in the text. Anchor = first <=5-word run that's not pure
  // stop-words; we fall back to a 24-char prefix.
  const rules: { agent: PersonaId; pattern: RegExp }[] = [];
  for (const v of vectors) {
    const pat = anchorRegex(v.angle);
    if (pat) rules.push({ agent: v.agent_id, pattern: pat });
  }
  if (rules.length === 0) return <>{text}</>;

  // Walk text, find earliest match from any rule, recurse.
  const out: Array<string | { agent: PersonaId; content: string }> = [];
  let cursor = 0;
  while (cursor < text.length) {
    let best: { idx: number; len: number; agent: PersonaId } | null = null;
    for (const r of rules) {
      r.pattern.lastIndex = 0;
      const m = r.pattern.exec(text.slice(cursor));
      if (m && m.index >= 0) {
        const abs = cursor + m.index;
        if (!best || abs < cursor + (best.idx - cursor)) {
          best = { idx: abs, len: m[0].length, agent: r.agent };
        }
      }
    }
    if (!best) {
      out.push(text.slice(cursor));
      break;
    }
    if (best.idx > cursor) out.push(text.slice(cursor, best.idx));
    out.push({ agent: best.agent, content: text.slice(best.idx, best.idx + best.len) });
    cursor = best.idx + best.len;
  }
  return (
    <>
      {out.map((chunk, i) =>
        typeof chunk === "string" ? (
          <span key={i}>{chunk}</span>
        ) : (
          <span key={i} className="marked marked-active">
            {chunk.content}
            <sup className="marked-sup j-mono">[{chunk.agent}]</sup>
          </span>
        ),
      )}
    </>
  );
}

function anchorRegex(angle: string): RegExp | null {
  // Extract a phrase: look for "§N", "fig.N", or a quoted substring first.
  const secRef = angle.match(/§\d+(?:\.\d+)?/);
  if (secRef) return new RegExp(escapeRegex(secRef[0]), "g");
  const quoted = angle.match(/"([^"]{6,48})"/);
  if (quoted) return new RegExp(escapeRegex(quoted[1]), "g");
  // Fallback: first 4-6 substantive words.
  const words = angle.split(/\s+/).filter((w) => w.length > 2);
  const anchor = words.slice(0, 5).join(" ");
  if (anchor.length < 8) return null;
  return new RegExp(escapeRegex(anchor.slice(0, 48)), "gi");
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
