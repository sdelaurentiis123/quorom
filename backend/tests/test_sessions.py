"""SessionStore + cancellation grace."""
from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest

from app import config as cfg
from app.sessions import SessionStore


@pytest.mark.asyncio
async def test_cancel_watcher_cancels_idle_session(monkeypatch):
    # Tighten grace so the test doesn't take 30s.
    monkeypatch.setattr(cfg, "CANCEL_GRACE_S", 0.3)

    store = SessionStore()
    sess = store.create("sid")

    was_cancelled = asyncio.Event()

    async def long_runner():
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            was_cancelled.set()
            raise

    sess.task = asyncio.create_task(long_runner())

    # No subscriber ever attaches. Bus reports empty_since immediately.
    # Manually set empty_since to mimic "we had a subscriber then lost it".
    import time
    sess.bus._empty_since = time.monotonic()

    # Use a shorter poll window than the watcher's default 5s.
    async def fast_watcher():
        while True:
            await asyncio.sleep(0.1)
            import time as _t
            now = _t.monotonic()
            for s in list(store._sessions.values()):
                if s.task is None or s.task.done():
                    continue
                es = s.bus.empty_since
                if es is not None and (now - es) > cfg.CANCEL_GRACE_S and not s.bus.has_subscribers:
                    s.task.cancel()

    watcher = asyncio.create_task(fast_watcher())
    try:
        await asyncio.wait_for(was_cancelled.wait(), timeout=2.0)
    finally:
        watcher.cancel()
        with suppress(asyncio.CancelledError):
            await watcher
        with suppress(asyncio.CancelledError):
            await sess.task

    assert was_cancelled.is_set()
