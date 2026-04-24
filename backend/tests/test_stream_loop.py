"""stream_loop — tool-use dispatch, commit validation, placeholder on exhaustion.

Uses a fake AsyncAnthropic whose `messages.stream(...)` yields scripted events
and whose `get_final_message()` returns a scripted Message. This is the shape
we depend on from the real SDK; if Anthropic changes it, these tests will go
red and we re-align.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.llm.stream_loop import default_validate_commit_finding, run_agent_loop


# ────────────────────────────────────────
# Fake Anthropic SDK
# ────────────────────────────────────────

@dataclass
class FakeBlock:
    type: str
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)
    text: str = ""


@dataclass
class FakeDelta:
    type: str
    text: str = ""
    partial_json: str = ""


@dataclass
class FakeEvent:
    type: str
    content_block: Any = None
    delta: Any = None
    index: int = 0


@dataclass
class FakeMessage:
    stop_reason: str
    content: list[FakeBlock]


class FakeStream:
    def __init__(self, events: list[FakeEvent], final: FakeMessage):
        self._events = events
        self._final = final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def __aiter__(self):
        self._it = iter(self._events)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration

    async def get_final_message(self):
        return self._final


class FakeMessages:
    def __init__(self, scripts: list[tuple[list[FakeEvent], FakeMessage]]):
        self._scripts = iter(scripts)

    def stream(self, **kwargs):
        events, final = next(self._scripts)
        return FakeStream(events, final)


class FakeClient:
    def __init__(self, scripts):
        self.messages = FakeMessages(scripts)


# ────────────────────────────────────────
# Tests
# ────────────────────────────────────────

@pytest.mark.asyncio
async def test_text_delta_emits_think_per_newline():
    traces: list[dict] = []

    async def on_trace(t): traces.append(t)
    async def dispatch(n, i, _t): return {"ok": True}

    events = [
        FakeEvent(type="content_block_delta", delta=FakeDelta(type="text_delta", text="first line\n")),
        FakeEvent(type="content_block_delta", delta=FakeDelta(type="text_delta", text="second ")),
        FakeEvent(type="content_block_delta", delta=FakeDelta(type="text_delta", text="line\n")),
    ]
    final = FakeMessage(stop_reason="end_turn", content=[])
    client = FakeClient([(events, final)])

    res = await run_agent_loop(
        client=client, model="x", system="s", user_msg="u", tools=[],
        on_trace=on_trace, dispatch_tool=dispatch,
        commit_tool_name="commit_finding", max_turns=1,
    )
    assert res is None
    kinds = [t["kind"] for t in traces]
    texts = [t["text"] for t in traces]
    assert kinds == ["think", "think"]
    assert texts == ["first line", "second line"]


@pytest.mark.asyncio
async def test_tool_use_dispatches_and_continues():
    traces: list[dict] = []
    dispatched: list[tuple[str, dict]] = []

    async def on_trace(t): traces.append(t)
    async def dispatch(n, i, _t):
        dispatched.append((n, i))
        return {"ok": True, "hits": 3}

    # Turn 1: model calls arxiv_search, stop_reason=tool_use.
    # Tool args stream in via input_json_delta; we emit the tool trace at
    # content_block_stop now (R4), so the simulated events must include them.
    turn1_events = [
        FakeEvent(type="content_block_start", index=0, content_block=FakeBlock(type="tool_use", name="arxiv_search", id="tu1")),
        FakeEvent(type="content_block_delta", index=0, delta=FakeDelta(type="input_json_delta", partial_json='{"query":"foo"}')),
        FakeEvent(type="content_block_stop", index=0),
    ]
    turn1_final = FakeMessage(stop_reason="tool_use", content=[
        FakeBlock(type="tool_use", name="arxiv_search", id="tu1", input={"query": "foo"}),
    ])
    # Turn 2: model commits
    turn2_events = []
    turn2_final = FakeMessage(stop_reason="tool_use", content=[
        FakeBlock(type="tool_use", name="commit_finding", id="tu2",
                  input={"id": "STAT", "sev": "high", "title": "t", "text": "x", "section": "§4"}),
    ])
    client = FakeClient([(turn1_events, turn1_final), (turn2_events, turn2_final)])

    res = await run_agent_loop(
        client=client, model="x", system="s", user_msg="u", tools=[],
        on_trace=on_trace, dispatch_tool=dispatch,
        commit_tool_name="commit_finding",
        validate_commit=default_validate_commit_finding, max_turns=3,
    )
    assert res is not None
    assert res["id"] == "STAT"
    assert ("arxiv_search", {"query": "foo"}) in dispatched
    # Must have emitted the tool + commit traces
    kinds = [t["kind"] for t in traces]
    assert "tool" in kinds
    assert "commit" in kinds


@pytest.mark.asyncio
async def test_commit_finding_with_invalid_id_is_refused():
    traces: list[dict] = []

    async def on_trace(t): traces.append(t)
    async def dispatch(n, i, _t): return {}

    # Invalid persona id. Loop should refuse, append is_error tool_result,
    # then advance to next turn which... we only have one turn, so returns None.
    turn1_events = []
    turn1_final = FakeMessage(stop_reason="tool_use", content=[
        FakeBlock(type="tool_use", name="commit_finding", id="bad",
                  input={"id": "BOGUS", "sev": "high", "title": "t", "text": "x", "section": "§1"}),
    ])
    turn2_events = []
    turn2_final = FakeMessage(stop_reason="end_turn", content=[])
    client = FakeClient([(turn1_events, turn1_final), (turn2_events, turn2_final)])

    res = await run_agent_loop(
        client=client, model="x", system="s", user_msg="u", tools=[],
        on_trace=on_trace, dispatch_tool=dispatch,
        commit_tool_name="commit_finding",
        validate_commit=default_validate_commit_finding, max_turns=3,
    )
    assert res is None
    # Must have flagged the refusal
    assert any(t["kind"] == "flag" and "refused" in t["text"] for t in traces)


@pytest.mark.asyncio
async def test_exhausted_turns_returns_none():
    async def on_trace(_t): pass
    async def dispatch(_n, _i, _t): return {}

    # Each turn: dispatch a tool (never commits), loop eventually exhausts.
    def make_turn():
        return ([], FakeMessage(stop_reason="tool_use", content=[
            FakeBlock(type="tool_use", name="arxiv_search", id="t", input={"query": "x"}),
        ]))
    client = FakeClient([make_turn() for _ in range(3)])

    res = await run_agent_loop(
        client=client, model="x", system="s", user_msg="u", tools=[],
        on_trace=on_trace, dispatch_tool=dispatch,
        commit_tool_name="commit_finding", max_turns=3,
    )
    assert res is None


@pytest.mark.asyncio
async def test_flag_tool_emits_flag_trace_not_commit():
    traces: list[dict] = []

    async def on_trace(t): traces.append(t)
    async def dispatch(_n, _i, _t): return {}

    turn1_events = []
    turn1_final = FakeMessage(stop_reason="tool_use", content=[
        FakeBlock(type="tool_use", name="flag", id="f1", input={"text": "suspicious claim"}),
    ])
    turn2_events = []
    turn2_final = FakeMessage(stop_reason="tool_use", content=[
        FakeBlock(type="tool_use", name="commit_finding", id="c1",
                  input={"id": "STAT", "sev": "high", "title": "t", "text": "x", "section": "§4"}),
    ])
    client = FakeClient([(turn1_events, turn1_final), (turn2_events, turn2_final)])

    res = await run_agent_loop(
        client=client, model="x", system="s", user_msg="u", tools=[],
        on_trace=on_trace, dispatch_tool=dispatch,
        commit_tool_name="commit_finding",
        validate_commit=default_validate_commit_finding, max_turns=3,
    )
    assert res is not None
    flags = [t for t in traces if t["kind"] == "flag"]
    assert any("suspicious" in f["text"] for f in flags)
