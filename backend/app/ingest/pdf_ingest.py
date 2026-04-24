"""PDF → text extraction.

Primary path: pymupdf4llm (returns markdown with headings/layout preserved).
Fallback: pypdf (raw text + de-hyphenation).
"""
from __future__ import annotations

import io
import logging
import re
import tempfile
from pathlib import Path

log = logging.getLogger("quorum.ingest.pdf")


def extract_markdown(pdf_bytes: bytes) -> tuple[str, str]:
    """Return (text, format). Format is 'markdown' on success, 'text' on fallback."""
    try:
        import pymupdf4llm  # noqa: PLC0415
        # pymupdf4llm wants a path; write to a tempfile.
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            path = f.name
        try:
            md = pymupdf4llm.to_markdown(path, show_progress=False)
        finally:
            try:
                Path(path).unlink()
            except OSError:
                pass
        md = _clean_markdown(md)
        if md.strip():
            return md, "markdown"
    except Exception as e:
        log.warning("pymupdf4llm failed, falling back to pypdf: %s", e)
    # Fallback path
    return extract_text(pdf_bytes), "text"


def extract_text(pdf_bytes: bytes) -> str:
    import pypdf  # noqa: PLC0415
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    raw = "\n".join(pages)
    return _dehyphenate(raw)


def _dehyphenate(text: str) -> str:
    text = re.sub(r"-\n\s*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _clean_markdown(md: str) -> str:
    # Collapse repeated blank lines and trim figure-caption noise.
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()
