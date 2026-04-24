"""Fetch arXiv metadata + PDF, extract body text. Validates Content-Type so
withdrawn papers (which return HTML from arxiv.org) surface as a clean error."""
from __future__ import annotations

import asyncio
import logging
import re

import arxiv
import httpx

from . import pdf_ingest

log = logging.getLogger("quorum.ingest.arxiv")

_client = arxiv.Client(page_size=1, delay_seconds=1, num_retries=2)


def normalize_arxiv_id(s: str) -> str:
    """Accepts 2604.01188, 2604.01188v2, arxiv.org/abs/2604.01188, etc."""
    s = s.strip()
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?$", s)
    return m.group(1) if m else s


async def fetch_arxiv(arxiv_id: str) -> tuple[dict, str, bytes]:
    """Returns (paper_dict, full_body_text, pdf_bytes). Raises IngestError on failure."""
    arxiv_id = normalize_arxiv_id(arxiv_id)

    def _meta() -> arxiv.Result | None:
        try:
            for r in _client.results(arxiv.Search(id_list=[arxiv_id])):
                return r
        except Exception as e:
            log.warning("arxiv meta lookup failed: %s", e)
        return None

    rec = await asyncio.to_thread(_meta)
    if rec is None:
        raise IngestError(f"arxiv paper {arxiv_id!r} not found")

    pdf_url = rec.pdf_url
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(pdf_url)

    ctype = (resp.headers.get("content-type") or "").lower()
    if "application/pdf" not in ctype:
        raise IngestError(
            f"arxiv did not return a PDF for {arxiv_id} (got {ctype!r}). "
            f"The paper may be withdrawn."
        )
    if resp.status_code != 200:
        raise IngestError(f"arxiv PDF fetch returned HTTP {resp.status_code}")

    pdf_bytes = resp.content
    body, fmt = pdf_ingest.extract_markdown(pdf_bytes)

    paper = {
        "id": rec.get_short_id(),
        "title": rec.title or "(untitled)",
        "authors": ", ".join(a.name for a in rec.authors[:6]),
        "venue": (f"arXiv · {rec.published.year}" if rec.published else "arXiv · preprint"),
        "abstract": rec.summary or "",
        "sections": [],  # filled by sectionize
        "body": body[:60_000],  # 60k chars ≈ 15k tokens; enough for UI + LLM
        "body_format": fmt,
        "has_pdf": True,
    }
    return paper, body, pdf_bytes


class IngestError(Exception):
    """Clean error — ingestion failed, user should see a toast."""
    pass
