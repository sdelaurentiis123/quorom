"""Session create / fetch / upload routes.

For M1–M3 we wire the mock runner; M9 swaps in the real session_runner.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from .. import config
from ..sessions import store
from ..mock_runner import run_mock_session
from ..session_runner import run_session

router = APIRouter()

# Uploaded PDF bytes live here for ~10 minutes, keyed by upload_id.
# Replaced by a real in-memory dict keyed by uuid at M8.
_uploads: dict[str, bytes] = {}


@router.post("/api/uploads")
async def upload_pdf(file: UploadFile = File(...)) -> dict[str, str]:
    if not (file.content_type or "").lower().startswith("application/pdf"):
        raise HTTPException(400, f"expected application/pdf, got {file.content_type}")
    data = await file.read()
    if len(data) > 40 * 1024 * 1024:
        raise HTTPException(413, "file too large (>40MB)")
    upload_id = uuid.uuid4().hex
    _uploads[upload_id] = data
    return {"upload_id": upload_id, "bytes": str(len(data))}


@router.post("/api/sessions")
async def create_session(payload: dict[str, Any]) -> dict[str, Any]:
    """Accepts {source: {kind: 'arxiv'|'pdf'|'demo', id?, upload_id?}}."""
    source = payload.get("source") or {}
    kind = source.get("kind")

    if kind == "arxiv":
        if not source.get("id"):
            raise HTTPException(400, "arxiv source requires id")
    elif kind == "pdf":
        uid = source.get("upload_id")
        if not uid or uid not in _uploads:
            raise HTTPException(400, "unknown upload_id")
    elif kind == "demo":
        pass
    else:
        raise HTTPException(400, f"unknown source kind: {kind!r}")

    session_id = uuid.uuid4().hex[:12]
    sess = store.create(session_id, source=source)

    # Pick runner. Mock runner is still available for dev demos without
    # burning Anthropic tokens: pass source={"kind":"demo","mock":true}.
    use_mock = bool(source.get("mock")) or not config.ANTHROPIC_API_KEY
    runner = run_mock_session(sess) if use_mock else run_session(sess)
    sess.task = asyncio.create_task(runner)

    return {"session_id": session_id, "source": source, "mock": use_mock}


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    sess = store.get(session_id)
    if not sess:
        raise HTTPException(404, "session not found")
    return {
        "session_id": sess.id,
        "paper": sess.paper,
        "vectors": sess.vectors,
        "findings": sess.findings,
        "verdict": sess.verdict,
        "last_seq": sess.bus.last_seq,
    }


def get_upload(upload_id: str) -> bytes | None:
    """Hook for ingest code to fetch upload bytes."""
    return _uploads.get(upload_id)
