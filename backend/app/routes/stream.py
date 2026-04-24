"""SSE stream endpoint. Subscribes a queue to SessionBus and emits text/event-stream."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..sessions import store

router = APIRouter()


@router.get("/api/sessions/{session_id}/stream")
async def stream(session_id: str, request: Request, since_seq: int = 0):
    sess = store.get(session_id)
    if not sess:
        raise HTTPException(404, "session not found")

    async def gen():
        async for ev in sess.bus.subscribe(since_seq=since_seq):
            if await request.is_disconnected():
                break
            data = json.dumps(ev, separators=(",", ":"))
            yield f"event: {ev['type']}\ndata: {data}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
