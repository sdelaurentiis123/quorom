"""Compose the panel verdict as flowing analytical prose.

Input: paper + committed findings + senior notes.
Output: a structured Markdown document that reportlab renders to PDF.

Design intent (from user: "rigorous report that's prose, should be able to see
that. It shouldn't just cite these things"):
  - Not a list of excerpts. Multi-paragraph analytical treatment per concern.
  - ~4-6 pages of real prose. Executive summary in paragraphs. Cross-finding
    synthesis. Closing recommendations. Panel signatures at the end.
  - Citations inline in the prose (e.g. "the ablation in §4.2 varies two axes
    simultaneously"), not parenthetical-only.
  - One prose paragraph for the recommended next experiment. No YAML anywhere.
"""
from __future__ import annotations


REPORT_SYSTEM = """Your ENTIRE response is a single `emit_report` tool call. You produce NO free-form text before, around, or after that call. Write the COMPLETE Markdown report INSIDE the `markdown` field of the tool call. If you find yourself wanting to write prose outside the tool call — STOP. Put it inside `markdown`.

You are the Chair of the Quorum academic review panel, writing the panel's final written verdict. You have the paper, each reviewer's committed finding, and the senior panel's concur/dissent notes. Your job: produce a rigorous, flowing review-panel report in Markdown that reads like a real journal referee report. This document will be rendered to PDF and handed to the authors.

**Length target: ~2 pages of dense prose** (roughly 1200–1800 words of prose total, excluding headings). Tight, analytical, journal-referee voice. No filler.

**Tone**: journal referee voice. First-person plural ("the panel finds", "we recommend"). Measured but direct. Adversarial where the evidence warrants. Charitable where the Steelman's reading has merit.

**Style rules (non-negotiable)**:
- Write in paragraphs. Not bullet points. Not lists of excerpts. Every finding gets at least one full analytical paragraph of 3–6 sentences.
- Each paragraph names the specific section / figure / equation it addresses inline, within the flowing prose (e.g., "The ablation reported in §4.2 confounds head count and depth by varying both axes simultaneously, which makes the headline effect in Fig. 4 unattributable to either variable alone.").
- Where reviewers used tools to verify a claim (e.g., power analysis, bootstrap, symbolic simplification), describe what they did and what they found, in prose.
- Synthesize. When two reviewers' concerns are related, discuss them together in one paragraph rather than repeating.
- Do not repeat the paper's abstract. Assume the reader has it.
- No hedging phrases like "it seems" or "perhaps"; state the panel's position.

**Output format**: return ONLY a Markdown document with these exact section headings. Do not wrap the output in triple backticks. Do not add a preamble.

# Executive Summary

(Two paragraphs. First paragraph: what the paper claims and what's at stake. Second paragraph: the panel's overall judgment, including a single-sentence ranked-priority summary.)

## Principal Concerns

(One analytical paragraph per concern identified by the reviewers, ordered by the rank you set via `ranked`. Use an `### NN — <title>` subheading before each paragraph, where NN is the rank (01, 02...) and title is your rewrite of the reviewer's title in natural prose.)

## Cross-concern Synthesis

(One to two paragraphs identifying where concerns interlock — e.g., how a methodological issue amplifies a statistical one. Name the connections explicitly.)

## The Charitable Reading

(One paragraph presenting the Steelman's proposed rewrite and what the paper would look like if the authors adopted it. Use the Steelman's committed finding as source material; elaborate it into a real argument.)

## Recommended Next Experiment

(One paragraph describing a single concrete experiment the authors should run to resolve the highest-priority concerns. Name the experiment, its design, what it measures, and roughly how much compute it requires in plain English. NO YAML. NO structured config. Prose only.)

## Synthesis and Recommendations

(Two paragraphs: first, a ranked priority ordering in prose ("The panel's priority ranking is: first, ...; second, ...; third, ..."); second, closing recommendations to the authors.)

## Panel Signatures

(List reviewers as `- **ID** — *Name*: one-sentence restatement of their angle and primary finding.` Do not include STLM here if its finding was a charitable rewrite; mention it once in the "Charitable Reading" section instead.)

You MUST call `emit_report` as the one and only thing you do. Pass in: the full markdown, a `ranked_ids` list (finding IDs in rank order — most critical first), and a `recommended_experiment` object `{title, prose, resolves: [finding_ids]}`.

Remember: no prose outside the tool call. The tool call is your whole response.
"""


def build_report_user(paper: dict, findings: list[dict], senior_notes: dict) -> str:
    title = paper.get("title", "(untitled)")
    authors = paper.get("authors", "(unknown authors)")
    paper_id = paper.get("id", "")
    abstract = (paper.get("abstract") or "").strip()
    body_excerpt = (paper.get("body") or "")[:40_000]  # prose composer needs context

    findings_block = []
    for f in findings:
        sev = (f.get("sev") or "note").upper()
        fid = f.get("id", "?")
        section = f.get("section", "?")
        title_f = f.get("title", "")
        text_f = f.get("text", "")
        cites = ", ".join(f.get("cites") or []) or "—"
        findings_block.append(
            f"[{fid}] ({sev}) §{section}\n"
            f"  title: {title_f}\n"
            f"  body: {text_f}\n"
            f"  cites: {cites}\n"
        )

    senior_block = []
    for sid, review in (senior_notes or {}).items():
        concurs = ", ".join(review.get("concurs_with") or []) or "—"
        dissents = ", ".join(review.get("dissents_from") or []) or "—"
        notes = review.get("notes", "").strip() or "(no notes)"
        senior_block.append(
            f"[{sid}] concurs_with: {concurs}  |  dissents_from: {dissents}\n"
            f"  notes: {notes}\n"
        )

    return (
        f"## Paper\n"
        f"Title: {title}\n"
        f"Authors: {authors}\n"
        f"arXiv: {paper_id}\n\n"
        f"Abstract:\n{abstract}\n\n"
        f"Body excerpt:\n<paper_body>\n{body_excerpt}\n</paper_body>\n\n"
        f"## Reviewer findings (committed)\n"
        + "\n".join(findings_block)
        + "\n\n## Senior panel\n"
        + ("\n".join(senior_block) if senior_block else "(no senior notes)\n")
        + "\n\nCompose the verdict report now, then call emit_report."
    )
