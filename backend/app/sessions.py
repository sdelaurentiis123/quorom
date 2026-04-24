"""In-memory session store + cancellation watcher.

The watcher runs every 5s. If a session has had no subscribers for
CANCEL_GRACE_S seconds AND its runner task is still running, we cancel
the task. Reviewer tool-loops catch CancelledError, emit a note-severity
placeholder finding, then re-raise, letting the gather unwind cleanly.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from . import config
from .bus import SessionBus

log = logging.getLogger("quorum.sessions")


@dataclass
class Session:
    id: str
    bus: SessionBus
    source: dict | None = None
    task: asyncio.Task | None = None
    paper: dict | None = None
    vectors: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    senior_notes: dict[str, Any] = field(default_factory=dict)
    verdict: dict | None = None
    error: str | None = None


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self, session_id: str, source: dict | None = None) -> Session:
        sess = Session(id=session_id, bus=SessionBus(session_id=session_id), source=source)
        self._sessions[session_id] = sess
        return sess

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def run_cancel_watcher(self) -> None:
        """Run until cancelled; periodically cancel idle sessions."""
        try:
            while True:
                await asyncio.sleep(5)
                now = time.monotonic()
                for sess in list(self._sessions.values()):
                    if sess.task is None or sess.task.done():
                        continue
                    es = sess.bus.empty_since
                    if es is not None and (now - es) > config.CANCEL_GRACE_S and not sess.bus.has_subscribers:
                        log.info("cancelling idle session %s", sess.id)
                        sess.task.cancel()
        except asyncio.CancelledError:
            return


store = SessionStore()
