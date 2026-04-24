"""SessionBus — publish/subscribe ordering, replay, cleanup, overflow."""
from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest

from app.bus import SessionBus


@pytest.mark.asyncio
async def test_publish_subscribe_ordering_and_seq_monotonic():
    bus = SessionBus(session_id="s1")
    received: list[dict] = []

    async def consumer():
        async for ev in bus.subscribe():
            received.append(ev)
            if len(received) == 3:
                return

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)  # let subscribe register

    bus.publish({"type": "phase.change", "phase": "intake"})
    bus.publish({"type": "phase.change", "phase": "reading"})
    bus.publish({"type": "phase.change", "phase": "deliberation"})

    await asyncio.wait_for(task, timeout=1.0)
    assert [e["seq"] for e in received] == [1, 2, 3]
    assert [e["phase"] for e in received] == ["intake", "reading", "deliberation"]
    assert all(e["session_id"] == "s1" for e in received)


@pytest.mark.asyncio
async def test_since_seq_replay_on_reconnect():
    bus = SessionBus(session_id="s2")
    for i in range(5):
        bus.publish({"type": "agent.trace", "i": i})

    received: list[dict] = []

    async def consumer():
        async for ev in bus.subscribe(since_seq=3):
            received.append(ev)
            if len(received) == 2:
                return

    await asyncio.wait_for(consumer(), timeout=1.0)
    assert [e["seq"] for e in received] == [4, 5]


@pytest.mark.asyncio
async def test_subscriber_cleanup_on_cancel_no_leak():
    bus = SessionBus(session_id="s3")

    async def consumer():
        async for _ in bus.subscribe():
            pass

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)
    assert bus.has_subscribers is True

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert bus.has_subscribers is False
    assert bus.empty_since is not None


@pytest.mark.asyncio
async def test_queue_full_emits_overflow():
    """When a subscriber's queue fills, _overflow is emitted; normal flow survives."""
    from app import config as cfg
    original = cfg.SUBSCRIBER_QUEUE_MAX
    cfg.SUBSCRIBER_QUEUE_MAX = 3
    try:
        bus = SessionBus(session_id="s4")

        # Subscribe but never consume — queue fills fast.
        gen = bus.subscribe()
        first_task = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0)

        # Flood past the queue size.
        for i in range(10):
            bus.publish({"type": "agent.trace", "i": i})

        # Drain the generator and collect what we got.
        collected = []
        try:
            first = await asyncio.wait_for(first_task, timeout=0.5)
            collected.append(first)
            while True:
                collected.append(await asyncio.wait_for(gen.__anext__(), timeout=0.1))
        except (asyncio.TimeoutError, StopAsyncIteration):
            pass
        finally:
            await gen.aclose()

        types = [e["type"] for e in collected]
        assert "_overflow" in types, f"expected _overflow in {types}"
    finally:
        cfg.SUBSCRIBER_QUEUE_MAX = original


@pytest.mark.asyncio
async def test_close_signals_end():
    bus = SessionBus(session_id="s5")

    async def consumer():
        count = 0
        async for _ in bus.subscribe():
            count += 1
        return count

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)
    bus.publish({"type": "x"})
    bus.close()
    result = await asyncio.wait_for(task, timeout=1.0)
    assert result == 1  # only the published event, then _end breaks the loop
