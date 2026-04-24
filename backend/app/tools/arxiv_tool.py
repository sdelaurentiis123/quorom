"""arxiv_search + arxiv_read via the `arxiv` Python package."""
from __future__ import annotations

import asyncio
import logging

import arxiv

log = logging.getLogger("quorum.tools.arxiv")

_client = arxiv.Client(page_size=10, delay_seconds=1, num_retries=2)


async def arxiv_search(query: str, k: int = 5) -> dict:
    """Top-k matching papers. Returns {results: [{id, title, authors, abstract}]}."""
    def _search() -> list[dict]:
        try:
            search = arxiv.Search(query=query, max_results=min(k, 10), sort_by=arxiv.SortCriterion.Relevance)
            out = []
            for r in _client.results(search):
                out.append({
                    "id": r.get_short_id(),
                    "title": r.title,
                    "authors": ", ".join(a.name for a in r.authors[:4]),
                    "abstract": (r.summary or "")[:600],
                })
            return out
        except Exception as e:
            log.warning("arxiv_search failed: %s", e)
            return []

    results = await asyncio.to_thread(_search)
    return {"ok": True, "results": results}


async def arxiv_read(arxiv_id: str) -> dict:
    """Fetch metadata + abstract for a single paper."""
    def _read() -> dict | None:
        try:
            search = arxiv.Search(id_list=[arxiv_id])
            for r in _client.results(search):
                return {
                    "id": r.get_short_id(),
                    "title": r.title,
                    "authors": ", ".join(a.name for a in r.authors),
                    "abstract": r.summary or "",
                    "published": r.published.isoformat() if r.published else None,
                    "pdf_url": r.pdf_url,
                }
            return None
        except Exception as e:
            log.warning("arxiv_read failed: %s", e)
            return None

    rec = await asyncio.to_thread(_read)
    if rec is None:
        return {"ok": False, "error": "not found"}
    return {"ok": True, **rec}
