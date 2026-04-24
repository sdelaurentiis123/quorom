"""Anthropic streaming tool-use loop.

One pass of `run_agent_loop`:
  1. stream a turn via `client.messages.stream(...)`
  2. map streaming events to on_trace emissions:
       - content_block_start (tool_use) → {kind: "tool", ...}
       - content_block_delta (text_delta) → {kind: "think", ...} per newline flush
  3. get_final_message(); if stop_reason != "tool_use", return
  4. otherwise execute each tool_use block, append tool_results, loop
  5. tenacity retry the whole turn on 429/529 with a `think` trace

The loop is generic — callers pass a `commit_tool_name` to designate the
terminal tool. Reviewers use "commit_finding"; seniors use "commit_senior_review";
the orchestrator uses a different shape (see prompts/orchestrator.py).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

import anthropic
from anthropic import AsyncAnthropic
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..types import PERSONA_IDS

log = logging.getLogger("quorum.stream_loop")

Trace = dict[str, Any]
OnTrace = Callable[[Trace], Awaitable[None] | None]
ToolHandler = Callable[[str, dict, OnTrace], Awaitable[dict]]

# Tool name rewriting for the UI: underscores → dotted form.
_DOTTED = {
    "arxiv_search": "arxiv.search",
    "arxiv_read": "arxiv.read",
    "s2_neighbors": "semanticscholar.neighbors",
    "s2_cites": "semanticscholar.cites",
    "sympy_simplify": "sympy.simplify",
    "sandbox_run": "sandbox.run",
    "power_calc": "power_calc",
    "bootstrap": "bootstrap",
}


def _fmt_tool_call(name: str, inp: dict) -> str:
    dotted = _DOTTED.get(name, name)
    # Keep the arg preview short so it fits the 72-char UI trace line.
    preview = ", ".join(f"{k}={_short(v)}" for k, v in list(inp.items())[:2])
    if len(preview) > 48:
        preview = preview[:45] + "…"
    return f"$ {dotted}({preview})"


def _short(v: Any) -> str:
    if isinstance(v, str):
        return json.dumps(v) if len(v) < 24 else json.dumps(v[:22] + "…")
    if isinstance(v, (int, float, bool)):
        return str(v)
    if isinstance(v, list):
        return f"[{len(v)}]" if len(v) > 3 else json.dumps(v)
    return type(v).__name__


async def _maybe_await(v: Any) -> None:
    if hasattr(v, "__await__"):
        await v


async def run_agent_loop(
    *,
    client: AsyncAnthropic,
    model: str,
    system: Any,  # str or list of blocks (for cache_control)
    user_msg: str,
    tools: list[dict],
    on_trace: OnTrace,
    dispatch_tool: ToolHandler,
    commit_tool_name: str,
    validate_commit: Callable[[dict], str | None] | None = None,
    max_turns: int = 10,
    max_tokens: int = 4096,
) -> dict | None:
    """Run the streaming tool-use loop until the commit tool fires or turns exhaust.

    Returns the commit tool's `input` dict on success, or None if the model
    exhausted turns / ended without committing.
    """
    messages: list[dict] = [{"role": "user", "content": user_msg}]

    for turn in range(max_turns):
        msg = await _one_turn(
            client=client,
            model=model,
            system=system,
            tools=tools,
            messages=messages,
            on_trace=on_trace,
            max_tokens=max_tokens,
        )

        if msg.stop_reason != "tool_use":
            # Model ended without using a tool. Look for a trailing commit
            # attempt in content blocks? No — the commit must be a tool call.
            return None

        tool_results: list[dict] = []
        for block in msg.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            name = block.name
            inp = dict(block.input) if block.input else {}

            if name == commit_tool_name:
                err = validate_commit(inp) if validate_commit else None
                if err:
                    await _maybe_await(on_trace({"kind": "flag", "text": f"refused: {err}"}))
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": f"refused: {err}. try again with a corrected value.",
                        "is_error": True,
                    })
                    continue
                sev = (inp.get("sev") or "note").upper()
                await _maybe_await(on_trace({"kind": "commit", "text": f"finding committed · severity: {sev}"}))
                return inp

            # flag is a first-class in-loop tool; it does not end the turn.
            if name == "flag":
                text = inp.get("text", "")
                await _maybe_await(on_trace({"kind": "flag", "text": text[:72]}))
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": "noted"})
                continue

            # Generic tool dispatch.
            try:
                result = await dispatch_tool(name, inp, on_trace)
            except Exception as e:  # pragma: no cover
                log.exception("tool %s failed", name)
                result = {"ok": False, "error": str(e)[:240]}

            payload = json.dumps(result)[:4000]
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": payload})

        # Feed results back for the next turn.
        messages.append({"role": "assistant", "content": msg.content})
        messages.append({"role": "user", "content": tool_results})

    # Ran out of turns without a commit.
    return None


async def _one_turn(*, client, model, system, tools, messages, on_trace, max_tokens):
    """Run one turn through the streaming API with retry on 429/529."""
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((
            anthropic.RateLimitError,
            anthropic.APIStatusError,
            anthropic.APIConnectionError,
        )),
        reraise=True,
    ):
        with attempt:
            try:
                return await _stream_once(
                    client=client, model=model, system=system, tools=tools,
                    messages=messages, on_trace=on_trace, max_tokens=max_tokens,
                )
            except (anthropic.RateLimitError, anthropic.APIStatusError) as e:
                status = getattr(e, "status_code", None)
                if status in (429, 529) or isinstance(e, anthropic.RateLimitError):
                    await _maybe_await(on_trace({
                        "kind": "think", "text": f"rate-limited ({status or '429'}); retrying…",
                    }))
                    raise
                raise
    raise RuntimeError("unreachable")


async def _stream_once(*, client, model, system, tools, messages, on_trace, max_tokens):
    """One streaming invocation. Returns the final Message object."""
    text_buf = ""
    async with client.messages.stream(
        model=model,
        system=system,
        tools=tools,
        max_tokens=max_tokens,
        messages=messages,
    ) as stream:
        async for event in stream:
            etype = getattr(event, "type", None)
            if etype == "content_block_start":
                cb = getattr(event, "content_block", None)
                if cb is not None and getattr(cb, "type", None) == "tool_use":
                    name = cb.name
                    # We don't have args yet (they stream in as input_json_delta).
                    # Emit a minimal tool trace; subsequent text_delta may elaborate.
                    if name == "flag":
                        pass  # wait for full input to get the flag text
                    elif name not in ("commit_finding", "commit_senior_review", "emit_vector", "emit_verdict"):
                        await _maybe_await(on_trace({"kind": "tool", "text": _fmt_tool_call(name, {})}))
            elif etype == "content_block_delta":
                delta = getattr(event, "delta", None)
                if delta is None:
                    continue
                dtype = getattr(delta, "type", None)
                if dtype == "text_delta":
                    txt = getattr(delta, "text", "") or ""
                    text_buf += txt
                    while "\n" in text_buf:
                        line, text_buf = text_buf.split("\n", 1)
                        line = line.strip()
                        if line:
                            await _maybe_await(on_trace({"kind": "think", "text": line[:72]}))
            # Other event types (message_start, message_delta, message_stop,
            # content_block_stop, input_json_delta) don't produce traces directly.

        msg = await stream.get_final_message()

    # Flush any tail text without newline as one last think line.
    tail = text_buf.strip()
    if tail:
        await _maybe_await(on_trace({"kind": "think", "text": tail[:72]}))

    return msg


def default_validate_commit_finding(inp: dict) -> str | None:
    """Ensure commit_finding.id ∈ PERSONA_IDS."""
    if inp.get("id") not in PERSONA_IDS:
        return f"id must be one of {PERSONA_IDS}"
    return None
