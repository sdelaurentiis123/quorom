"""Semantic Scholar — citation neighbors. Anonymous at ~1 req/sec, higher
with an S2_API_KEY. Best-effort: if S2 is slow or 429s, we degrade cleanly."""
from __future__ import annotations

import asyncio
import logging

import httpx

from .. import config

log = logging.getLogger("quorum.tools.s2")

_BASE = "https://api.semanticscholar.org/graph/v1"


def _headers() -> dict[str, str]:
    return {"x-api-key": config.S2_API_KEY} if config.S2_API_KEY else {}


async def s2_neighbors(arxiv_id: str, direction: str = "cited_by", k: int = 5) -> dict:
    """Return up to k neighbors. Paper id on S2 uses `ARXIV:<id>`."""
    paper_key = f"ARXIV:{arxiv_id}"
    endpoint = "references" if direction == "cites" else "citations"
    fields = "paperId,title,year,authors,abstract"
    url = f"{_BASE}/paper/{paper_key}/{endpoint}?fields={fields}&limit={min(k, 10)}"

    try:
        async with httpx.AsyncClient(timeout=6.0, headers=_headers()) as client:
            resp = await client.get(url)
            if resp.status_code == 429:
                await asyncio.sleep(1.2)
                resp = await client.get(url)
            if resp.status_code != 200:
                return {"ok": False, "error": f"HTTP {resp.status_code}"}
            data = resp.json() or {}
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"network: {e}"}

    papers = []
    for row in (data.get("data") or [])[:k]:
        p = row.get("citedPaper") if direction == "cites" else row.get("citingPaper")
        if not p:
            continue
        papers.append({
            "id": p.get("paperId", ""),
            "title": p.get("title", ""),
            "year": p.get("year"),
            "authors": ", ".join((a.get("name") or "") for a in (p.get("authors") or [])[:3]),
            "abstract": (p.get("abstract") or "")[:400],
        })
    return {"ok": True, "direction": direction, "papers": papers}
