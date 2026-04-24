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
    """Format `tool.name(args)` for a trace line. Special-cased for sandbox_run
    and arxiv_search so the user sees the actual code/query, not empty parens."""
    dotted = _DOTTED.get(name, name)

    if name == "sandbox_run":
        code = (inp.get("code") or "").strip()
        if not code:
            return f"$ {dotted}(…)"
        # First non-trivial line of code is the most informative preview.
        first = next((ln.strip() for ln in code.splitlines() if ln.strip()), "")
        first = first[:110]
        return f"$ {dotted}\n  {first}"

    if name == "arxiv_search":
        q = inp.get("query", "")
        k = inp.get("k")
        preview = f"{json.dumps(q)}" if isinstance(q, str) else str(q)
        if k:
            return f"$ {dotted}({preview}, k={k})"
        return f"$ {dotted}({preview})"

    if name == "arxiv_read":
        return f"$ {dotted}({inp.get('arxiv_id','')!r})"

    if name == "s2_neighbors":
        return f"$ {dotted}({inp.get('arxiv_id','')!r}, direction={inp.get('direction','cited_by')!r})"

    if name == "bootstrap":
        data = inp.get("data", [])
        return f"$ {dotted}(data=[{len(data)}], B={inp.get('B', 2000)})"

    if name == "power_calc":
        return f"$ {dotted}(δ={inp.get('delta','?')}, α={inp.get('alpha',0.05)}, β={inp.get('beta',0.20)})"

    if name == "sympy_simplify":
        expr = inp.get("expr", "")
        preview = expr if len(expr) <= 54 else expr[:51] + "…"
        return f"$ {dotted}({preview!r})"

    # Fallback: first 2 args as key=value.
    preview = ", ".join(f"{k}={_short(v)}" for k, v in list(inp.items())[:2])
    if len(preview) > 80:
        preview = preview[:77] + "…"
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
    """Run one turn through the streaming API with retry on 429/529.
    Honors Anthropic's `retry-after` header on 429s."""
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
                    # Honor retry-after header if present (capped).
                    delay_s: float | None = None
                    resp = getattr(e, "response", None)
                    if resp is not None:
                        hdr = None
                        try:
                            hdr = resp.headers.get("retry-after")
                        except Exception:
                            pass
                        if hdr:
                            try:
                                delay_s = min(20.0, float(hdr))
                            except ValueError:
                                delay_s = None

                    msg = f"rate-limited ({status or '429'})"
                    if delay_s:
                        msg += f"; retrying in {delay_s:.0f}s"
                    else:
                        msg += "; retrying…"
                    await _maybe_await(on_trace({"kind": "think", "text": msg}))

                    if delay_s:
                        import asyncio as _asyncio
                        await _asyncio.sleep(delay_s)
                    raise
                raise
    raise RuntimeError("unreachable")


async def _stream_once(*, client, model, system, tools, messages, on_trace, max_tokens):
    """One streaming invocation. Returns the final Message object.

    We accumulate each tool_use block's input JSON deltas so that when the
    block closes we can emit a *meaningful* trace line — e.g.
        $ sandbox.run
          import numpy as np; print(np.std(...))
    instead of the earlier `$ sandbox.run()`.
    """
    text_buf = ""
    # index → {name, input_buf}
    block_buf: dict[int, dict[str, Any]] = {}
    async with client.messages.stream(
        model=model,
        system=system,
        tools=tools,
        max_tokens=max_tokens,
        messages=messages,
    ) as stream:
        async for event in stream:
            etype = getattr(event, "type", None)
            idx = getattr(event, "index", None)

            if etype == "content_block_start":
                cb = getattr(event, "content_block", None)
                if cb is not None and getattr(cb, "type", None) == "tool_use":
                    block_buf[idx] = {"name": cb.name, "input_buf": "", "emitted": False}

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
                            await _maybe_await(on_trace({"kind": "think", "text": line[:110]}))
                elif dtype == "input_json_delta":
                    # Partial JSON for the tool input. Buffer; parse on stop.
                    chunk = getattr(delta, "partial_json", "") or ""
                    if idx in block_buf:
                        block_buf[idx]["input_buf"] += chunk

            elif etype == "content_block_stop":
                bb = block_buf.pop(idx, None)
                if bb is not None and not bb["emitted"]:
                    name = bb["name"]
                    # Commit / meta tools — don't clutter the trace with their args;
                    # their own side-effects (agent.finding etc.) are visible.
                    if name in ("commit_finding", "commit_senior_review", "emit_vector", "emit_report", "emit_verdict"):
                        pass
                    elif name == "flag":
                        # Let run_agent_loop emit the flag trace with the actual text
                        # once the block closes in the outer loop's dispatch handling.
                        pass
                    else:
                        try:
                            parsed = json.loads(bb["input_buf"]) if bb["input_buf"].strip() else {}
                        except json.JSONDecodeError:
                            parsed = {}
                        # Emit a single, meaningful trace line per tool call.
                        text = _fmt_tool_call(name, parsed)
                        # Split on \n so the log renders code on its own line(s).
                        for piece in text.split("\n"):
                            if piece.strip():
                                await _maybe_await(on_trace({"kind": "tool", "text": piece[:140]}))
                    bb["emitted"] = True
            # message_start, message_delta, message_stop aren't surfaced.

        msg = await stream.get_final_message()

    # Flush any tail text without newline as one last think line.
    tail = text_buf.strip()
    if tail:
        await _maybe_await(on_trace({"kind": "think", "text": tail[:72]}))

    # Log cache behavior so we can see F1 working in real time.
    try:
        usage = getattr(msg, "usage", None)
        if usage is not None:
            log.info(
                "anthropic usage: input=%d  cache_read=%d  cache_create=%d  output=%d",
                getattr(usage, "input_tokens", 0),
                getattr(usage, "cache_read_input_tokens", 0) or 0,
                getattr(usage, "cache_creation_input_tokens", 0) or 0,
                getattr(usage, "output_tokens", 0),
            )
    except Exception:
        pass

    return msg


def default_validate_commit_finding(inp: dict) -> str | None:
    """Ensure commit_finding.id ∈ PERSONA_IDS."""
    if inp.get("id") not in PERSONA_IDS:
        return f"id must be one of {PERSONA_IDS}"
    return None
