"""Mock runner — full 5-phase state machine fires."""
from __future__ import annotations

import asyncio

import pytest

from app.mock_runner import run_mock_session
from app.sessions import SessionStore


@pytest.mark.asyncio
async def test_full_phase_sequence_emits_verdict():
    store = SessionStore()
    sess = store.create("test")

    collected: list[dict] = []

    async def consumer():
        async for ev in sess.bus.subscribe():
            collected.append(ev)
            if ev["type"] == "verdict.ready":
                return

    # Speed up the mock by patching asyncio.sleep to be shorter.
    original_sleep = asyncio.sleep

    async def fast_sleep(t):
        await original_sleep(min(t, 0.02))

    import app.mock_runner as mr
    mr.asyncio.sleep = fast_sleep  # type: ignore[attr-defined]

    try:
        consumer_task = asyncio.create_task(consumer())
        sess.task = asyncio.create_task(run_mock_session(sess))
        await asyncio.wait_for(consumer_task, timeout=10.0)
    finally:
        mr.asyncio.sleep = original_sleep  # type: ignore[attr-defined]
        sess.task.cancel()
        try:
            await sess.task
        except asyncio.CancelledError:
            pass

    types = [e["type"] for e in collected]
    # Must see all phase changes in order.
    phase_changes = [e for e in collected if e["type"] == "phase.change"]
    assert [p["phase"] for p in phase_changes] == [
        "intake", "reading", "deliberation", "converging", "verdict",
    ]
    assert "paper.extracted" in types
    # Panel is 5 seats now (METH, STAT, THRY, EMPR, STLM); HIST removed.
    # The real runner caps to 3 non-STLM + STLM = 4; the mock runs all 5 for visibility.
    assert types.count("vector.identified") == 5
    assert types.count("agent.finding") == 5
    assert types.count("senior.signed") == 3
    assert types[-1] == "verdict.ready"


@pytest.mark.asyncio
async def test_mock_runner_handles_cancellation():
    store = SessionStore()
    sess = store.create("test-cancel")

    sess.task = asyncio.create_task(run_mock_session(sess))
    await asyncio.sleep(0.1)
    sess.task.cancel()
    try:
        await sess.task
    except asyncio.CancelledError:
        pass

    # Bus should be closed after cancellation.
    assert sess.bus.is_closed
