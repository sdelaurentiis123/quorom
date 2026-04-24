"""POST /api/sessions/:id/chat — streams chat events over SSE."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..chat import chat_turn_stream
from ..sessions import store
from ..types import PERSONA_IDS

router = APIRouter()

ALLOWED_TARGETS = {"all", *PERSONA_IDS}


@router.post("/api/sessions/{session_id}/chat")
async def chat(session_id: str, request: Request, payload: dict):
    sess = store.get(session_id)
    if not sess:
        raise HTTPException(404, "session not found")

    target = payload.get("target", "all")
    message = (payload.get("message") or "").strip()
    if target not in ALLOWED_TARGETS:
        raise HTTPException(400, f"target must be one of {sorted(ALLOWED_TARGETS)}")
    if not message:
        raise HTTPException(400, "message is required")
    if not sess.findings:
        # 409 Conflict = "resource exists but not in the right state yet".
        # Frontend uses this to render "panel still deliberating" vs the
        # 404 state ("session ended — convene a new one").
        raise HTTPException(409, "panel has not produced findings yet — wait for verdict")

    async def gen():
        async for event in chat_turn_stream(sess, target=target, user_message=message):
            if await request.is_disconnected():
                break
            data = json.dumps(event, separators=(",", ":"))
            yield f"event: {event['type']}\ndata: {data}\n\n"
        yield "event: chat.finished\ndata: {}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
