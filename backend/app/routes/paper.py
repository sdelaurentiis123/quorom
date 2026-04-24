"""Serves the source PDF + generated verdict PDF for a session."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..sessions import store

router = APIRouter()


@router.get("/api/sessions/{session_id}/paper.pdf")
async def paper_pdf(session_id: str):
    sess = store.get(session_id)
    if not sess:
        raise HTTPException(404, "session not found")
    if not sess.paper_pdf_bytes:
        raise HTTPException(404, "paper PDF not yet ingested")
    return Response(
        content=sess.paper_pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="paper-{session_id}.pdf"',
            "Cache-Control": "private, max-age=60",
        },
    )


@router.get("/api/sessions/{session_id}/verdict.pdf")
async def verdict_pdf(session_id: str):
    sess = store.get(session_id)
    if not sess:
        raise HTTPException(404, "session not found")
    if not sess.verdict_pdf_bytes:
        raise HTTPException(404, "verdict PDF not yet generated")
    return Response(
        content=sess.verdict_pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="quorum-verdict-{session_id}.pdf"',
            "Cache-Control": "private, max-age=60",
        },
    )
