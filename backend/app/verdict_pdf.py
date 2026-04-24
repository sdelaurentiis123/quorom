"""Render the panel verdict report — Markdown → PDF via reportlab.

The LLM (see prompts/report.py) produces a structured Markdown document.
This module parses that Markdown into reportlab flowables and emits a
multi-page referee-report PDF with journal typography.

Supported Markdown subset (enough for our composer's output):
  - `# H1` — chapter heading (Cover is rendered separately; `# Executive Summary` etc.)
  - `## H2` — section heading
  - `### H3` — subsection heading (used for per-concern ranks)
  - Paragraph text — blank-line separated
  - Inline `*italic*`, `**bold**`, `§x.y`, `fig.N`, `eq.(N)` get accent highlighting
  - `- item` — bullet list (kept minimal; the prompt discourages bullets)
"""
from __future__ import annotations

import io
import re
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .types import PERSONAS

# ── Palette ────────────────────────────────────────────────────────────
PAPER = colors.HexColor("#F5EFE4")
PAPER2 = colors.HexColor("#EEE6D6")
INK = colors.HexColor("#2A241C")
INK2 = colors.HexColor("#5B5143")
INK3 = colors.HexColor("#8A7E6C")
RULE = colors.HexColor("#C9BDA5")
ACCENT = colors.HexColor("#B4542A")


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title", parent=base["Title"],
            fontName="Times-Italic", fontSize=40, leading=46,
            textColor=INK, alignment=TA_CENTER, spaceAfter=14,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", parent=base["Normal"],
            fontName="Courier", fontSize=11, leading=14,
            textColor=INK2, alignment=TA_CENTER, spaceAfter=4,
        ),
        "cover_paper_title": ParagraphStyle(
            "cover_paper_title", parent=base["Normal"],
            fontName="Times-Roman", fontSize=18, leading=23,
            textColor=INK, alignment=TA_CENTER, spaceAfter=10,
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta", parent=base["Normal"],
            fontName="Courier", fontSize=9, leading=12,
            textColor=INK2, alignment=TA_CENTER, spaceAfter=4,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"],
            fontName="Times-Italic", fontSize=22, leading=28,
            textColor=INK, spaceAfter=10, spaceBefore=18,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"],
            fontName="Times-Italic", fontSize=16, leading=20,
            textColor=INK, spaceAfter=8, spaceBefore=14,
        ),
        "h3": ParagraphStyle(
            "h3", parent=base["Heading3"],
            fontName="Times-Italic", fontSize=13, leading=17,
            textColor=INK, spaceAfter=4, spaceBefore=10,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"],
            fontName="Times-Roman", fontSize=11, leading=17,
            textColor=INK, alignment=TA_JUSTIFY, spaceAfter=10,
            firstLineIndent=0,
        ),
        "body_small": ParagraphStyle(
            "body_small", parent=base["Normal"],
            fontName="Times-Roman", fontSize=10, leading=14,
            textColor=INK2, alignment=TA_LEFT, spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=base["Normal"],
            fontName="Times-Roman", fontSize=11, leading=16,
            textColor=INK, leftIndent=18, bulletIndent=6,
            alignment=TA_LEFT, spaceAfter=4,
        ),
        "stamp": ParagraphStyle(
            "stamp", parent=base["Normal"],
            fontName="Courier", fontSize=11, leading=14,
            textColor=ACCENT, alignment=TA_CENTER,
        ),
    }


def generate_verdict_pdf(
    *,
    paper: dict,
    report_markdown: str,
    session_id: str,
    committed_agent_ids: list[str],
) -> bytes:
    """Render (cover + body from markdown + signatures) to a PDF byte string."""
    styles = _styles()
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=1.0 * inch, rightMargin=1.0 * inch,
        topMargin=1.0 * inch, bottomMargin=0.9 * inch,
        title=f"Quorum Panel Verdict — {(paper.get('title') or '(paper)')[:90]}",
        author="Quorum Review Panel",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="plain", frames=[frame], onPage=_page_deco)])

    story: list = []
    _add_cover(story, styles, paper, session_id)
    story.append(PageBreak())
    _render_markdown(story, styles, report_markdown)

    # If the markdown didn't include signatures (defensive), append them.
    if committed_agent_ids and not _markdown_has_section(report_markdown, "panel signatures"):
        story.append(PageBreak())
        _add_signatures(story, styles, committed_agent_ids)

    doc.build(story)
    return buf.getvalue()


# ── Markdown → flowables ───────────────────────────────────────────────

_SECTION_REF = re.compile(r"(§\d+(?:\.\d+)?|fig\.\s?\d+|eq\.?\s?\(\d+\)|Fig\.\s?\d+)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![*])\*(?!\*)([^*\n]+?)\*(?!\*)")


def _inline(text: str) -> str:
    """Convert a subset of inline markdown to reportlab Paragraph markup."""
    # escape reserved paragraph markup chars first
    t = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    t = _BOLD.sub(r"<b>\1</b>", t)
    t = _ITALIC.sub(r"<i>\1</i>", t)
    # highlight section refs subtly
    t = _SECTION_REF.sub(
        lambda m: f'<font color="{ACCENT.hexval()}">{m.group(0)}</font>',
        t,
    )
    return t


def _render_markdown(story: list, styles: dict, md: str) -> None:
    if not md:
        return
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Heading 1
        if stripped.startswith("# "):
            story.append(Paragraph(_inline(stripped[2:].strip()), styles["h1"]))
            i += 1
            continue
        # Heading 2
        if stripped.startswith("## "):
            story.append(Paragraph(_inline(stripped[3:].strip()), styles["h2"]))
            i += 1
            continue
        # Heading 3
        if stripped.startswith("### "):
            story.append(Paragraph(_inline(stripped[4:].strip()), styles["h3"]))
            i += 1
            continue

        # Bullet list (minimal)
        if stripped.startswith("- ") or stripped.startswith("* "):
            items = []
            while i < len(lines) and (lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")):
                items.append(lines[i].strip()[2:])
                i += 1
            for item in items:
                story.append(Paragraph(_inline(item), styles["bullet"], bulletText="•"))
            continue

        # Paragraph: merge until blank line
        para_lines = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not (
            lines[i].strip().startswith("#")
            or lines[i].strip().startswith("- ")
            or lines[i].strip().startswith("* ")
        ):
            para_lines.append(lines[i])
            i += 1
        text = " ".join(l.strip() for l in para_lines if l.strip())
        story.append(Paragraph(_inline(text), styles["body"]))


def _markdown_has_section(md: str, name_lower: str) -> bool:
    for line in md.splitlines():
        s = line.strip().lstrip("#").strip().lower()
        if s == name_lower:
            return True
    return False


# ── Cover + signatures + page frame ────────────────────────────────────

def _page_deco(canvas, doc):
    canvas.saveState()
    canvas.setFont("Courier", 7)
    canvas.setFillColor(INK3)
    canvas.drawString(doc.leftMargin, doc.pagesize[1] - 0.6 * inch,
                      "QUORUM  ·  ACADEMIC PANEL VERDICT")
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, doc.pagesize[1] - 0.6 * inch,
                           f"page {doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, doc.pagesize[1] - 0.65 * inch,
                doc.pagesize[0] - doc.rightMargin, doc.pagesize[1] - 0.65 * inch)
    canvas.restoreState()


def _add_cover(story: list, styles: dict, paper: dict, session_id: str) -> None:
    story.append(Spacer(1, 1.2 * inch))
    story.append(Paragraph("Quorum", styles["cover_title"]))
    story.append(Paragraph("ACADEMIC PANEL VERDICT", styles["cover_sub"]))
    story.append(Spacer(1, 0.5 * inch))
    story.append(_hr())
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph(_inline(paper.get("title", "(untitled paper)")), styles["cover_paper_title"]))
    story.append(Spacer(1, 0.1 * inch))
    authors = paper.get("authors") or "(author unknown)"
    story.append(Paragraph(f"<i>{_inline(authors)}</i>", styles["cover_meta"]))
    if paper.get("id"):
        story.append(Paragraph(f"arXiv: {_inline(paper['id'])}", styles["cover_meta"]))
    if paper.get("venue"):
        story.append(Paragraph(_inline(paper["venue"]), styles["cover_meta"]))
    story.append(Spacer(1, 0.5 * inch))
    story.append(_hr())
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph(
        f"session {session_id[:8]} · convened {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        styles["cover_meta"],
    ))
    story.append(Spacer(1, 0.4 * inch))
    story.append(Paragraph("quorum reached", styles["stamp"]))


def _hr():
    t = Table([[""]], colWidths=[6.5 * inch], rowHeights=[1])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.2, INK)]))
    return t


def _add_signatures(story: list, styles: dict, committed_ids: list[str]) -> None:
    story.append(Paragraph("Panel signatures", styles["h2"]))
    by_id = {p["id"]: p for p in PERSONAS}
    rows = []
    for pid in committed_ids:
        p = by_id.get(pid)
        if not p:
            continue
        rows.append([
            Paragraph(f"<font face='Courier' size=10><b>{pid}</b></font>", styles["body_small"]),
            Paragraph(f"<i>{_inline(p['name'])}</i>", styles["body_small"]),
            Paragraph(_inline(p["angle"]), styles["body_small"]),
        ])
    if rows:
        t = Table(rows, colWidths=[0.8 * inch, 1.7 * inch, 4.0 * inch])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, RULE),
        ]))
        story.append(t)
    story.append(Spacer(1, 0.25 * inch))
    story.append(Paragraph("— End of verdict —", styles["stamp"]))
