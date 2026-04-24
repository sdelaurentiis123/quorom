"""Post-verdict chat with the panel. Target: "all" or a single PersonaId.

Each agent carries its persona + paper excerpt + committed finding + chat
history. "all" fans out in parallel; responses interleave via their own
async generators combined into one stream.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator

from anthropic import AsyncAnthropic

from . import config
from .llm.client import get_client
from .sessions import Session
from .types import PERSONAS

log = logging.getLogger("quorum.chat")

MODEL_CHAT = config.MODEL_REVIEWER  # opus-4-7


def _persona_by_id(pid: str) -> dict | None:
    for p in PERSONAS:
        if p["id"] == pid:
            return p
    return None


def _agent_system(persona: dict, paper: dict, finding: dict | None) -> list[dict]:
    body = (paper or {}).get("body") or (paper or {}).get("abstract") or ""
    finding_block = ""
    if finding:
        finding_block = (
            f"\n\nYour committed finding from the session:\n"
            f"  id: {finding.get('id')}\n"
            f"  severity: {finding.get('sev','note').upper()}\n"
            f"  title: {finding.get('title','')}\n"
            f"  section: {finding.get('section','')}\n"
            f"  text: {finding.get('text','')}\n"
            f"  cites: {finding.get('cites', [])}\n"
        )
    return [
        {
            "type": "text",
            "text": (
                f"You are {persona['name']} ({persona['id']}) from the Quorum adversarial review panel. "
                f"Your angle: {persona['angle']}\n\n"
                f"The session is complete and your verdict has been rendered. A user is now asking you follow-up questions about the paper or your review. Respond tersely and technically — this is a post-mortem, not a lecture. Reference specific section / figure / equation numbers from the paper when relevant. If you don't know, say so.{finding_block}"
            ),
        },
        {
            "type": "text",
            "text": f"<paper>\n{body[:80_000]}\n</paper>",
            "cache_control": {"type": "ephemeral"},
        },
    ]


def _swarm_system(paper: dict, findings: list[dict]) -> list[dict]:
    body = (paper or {}).get("body") or (paper or {}).get("abstract") or ""
    findings_summary = "\n".join(
        f"  [{f.get('id')}] ({f.get('sev','note').upper()}) {f.get('title','')}"
        for f in findings
    )
    return [
        {
            "type": "text",
            "text": (
                "You are the Chair of the Quorum adversarial review panel, speaking on behalf of the whole panel after the verdict has been rendered. "
                "A user is asking the panel follow-up questions. Synthesize across the reviewers' angles. Reference agent IDs (METH/STAT/THRY/EMPR/STLM) when appropriate. "
                "Terse, technical, cite section/figure refs.\n\n"
                f"The panel's committed findings:\n{findings_summary}\n"
            ),
        },
        {
            "type": "text",
            "text": f"<paper>\n{body[:80_000]}\n</paper>",
            "cache_control": {"type": "ephemeral"},
        },
    ]


async def chat_turn_stream(
    sess: Session,
    target: str,
    user_message: str,
) -> AsyncIterator[dict]:
    """Yield chat events. Each event is a dict ready for SSE serialization.

    Events:
      {type: "chat.start", agent_id}
      {type: "chat.token", agent_id, delta}
      {type: "chat.done", agent_id, text}
    """
    client = get_client()

    # Append user message to the thread history.
    thread = sess.chat_threads.setdefault(target, [])
    thread.append({"role": "user", "text": user_message, "ts": time.time()})

    if target == "all":
        async for ev in _run_swarm(client, sess, user_message):
            yield ev
    else:
        async for ev in _run_single(client, sess, target, user_message):
            yield ev


async def _run_single(
    client: AsyncAnthropic,
    sess: Session,
    agent_id: str,
    user_message: str,
) -> AsyncIterator[dict]:
    persona = _persona_by_id(agent_id)
    if not persona:
        yield {"type": "chat.error", "agent_id": agent_id, "message": f"unknown agent {agent_id}"}
        return

    finding = next((f for f in sess.findings or [] if f.get("id", "").split("-")[0] == agent_id), None)
    system = _agent_system(persona, sess.paper or {}, finding)

    # Reconstruct the conversation from thread history (only roles/text).
    thread = sess.chat_threads.get(agent_id, [])
    messages = _thread_to_messages(thread, final_user=user_message)

    yield {"type": "chat.start", "agent_id": agent_id}
    text_buf = ""
    try:
        async with client.messages.stream(
            model=MODEL_CHAT,
            max_tokens=1800,  # single-agent replies can be long; don't truncate
            system=system,
            messages=messages,
        ) as stream:
            async for ev in stream:
                t = getattr(ev, "type", None)
                if t == "content_block_delta":
                    delta = getattr(ev, "delta", None)
                    if delta and getattr(delta, "type", None) == "text_delta":
                        txt = getattr(delta, "text", "") or ""
                        text_buf += txt
                        if txt:
                            yield {"type": "chat.token", "agent_id": agent_id, "delta": txt}
            await stream.get_final_message()
    except Exception as e:  # pragma: no cover
        log.exception("chat single %s failed", agent_id)
        yield {"type": "chat.error", "agent_id": agent_id, "message": str(e)[:200]}
        return

    thread.append({"role": "assistant", "agent_id": agent_id, "text": text_buf, "ts": time.time()})
    yield {"type": "chat.done", "agent_id": agent_id, "text": text_buf}


async def _run_swarm(
    client: AsyncAnthropic,
    sess: Session,
    user_message: str,
) -> AsyncIterator[dict]:
    """Fan out to every committed reviewer in parallel, interleave their streams."""
    committed = [
        (f.get("id", "").split("-")[0], f)
        for f in (sess.findings or [])
        if f.get("id")
    ]
    if not committed:
        yield {"type": "chat.error", "agent_id": "all", "message": "no committed reviewers to chat with"}
        return

    # Also run a chair-synthesis arm tagged as "CHAIR".
    chair_system = _swarm_system(sess.paper or {}, sess.findings or [])
    thread_all = sess.chat_threads.setdefault("all", [])
    chair_messages = _thread_to_messages(thread_all, final_user=user_message)

    queue: asyncio.Queue = asyncio.Queue(maxsize=256)

    async def drive_one(agent_id: str, system: list[dict], messages: list[dict]) -> None:
        await queue.put({"type": "chat.start", "agent_id": agent_id})
        text_buf = ""
        try:
            async with client.messages.stream(
                model=MODEL_CHAT,
                max_tokens=1500,  # enough headroom for a 4-5 sentence swarm reply
                system=system,
                messages=messages,
            ) as stream:
                async for ev in stream:
                    t = getattr(ev, "type", None)
                    if t == "content_block_delta":
                        delta = getattr(ev, "delta", None)
                        if delta and getattr(delta, "type", None) == "text_delta":
                            txt = getattr(delta, "text", "") or ""
                            if txt:
                                text_buf += txt
                                await queue.put({"type": "chat.token", "agent_id": agent_id, "delta": txt})
                await stream.get_final_message()
        except Exception as e:  # pragma: no cover
            await queue.put({"type": "chat.error", "agent_id": agent_id, "message": str(e)[:200]})
        await queue.put({"type": "chat.done", "agent_id": agent_id, "text": text_buf})

    tasks: list[asyncio.Task] = []
    # Chair first
    tasks.append(asyncio.create_task(drive_one("CHAIR", chair_system, chair_messages)))
    # Then each committed reviewer
    for agent_id, finding in committed:
        persona = _persona_by_id(agent_id)
        if not persona:
            continue
        system = _agent_system(persona, sess.paper or {}, finding)
        thread = sess.chat_threads.setdefault(agent_id, [])
        messages = _thread_to_messages(thread, final_user=user_message)
        tasks.append(asyncio.create_task(drive_one(agent_id, system, messages)))

    done_count = 0
    expected = len(tasks)
    completed_by_agent: dict[str, str] = {}
    try:
        while done_count < expected:
            event = await queue.get()
            yield event
            if event.get("type") == "chat.done":
                done_count += 1
                completed_by_agent[event["agent_id"]] = event.get("text", "")
    finally:
        # wait for remaining tasks to finalize
        for t in tasks:
            if not t.done():
                t.cancel()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

    # Persist assistant messages to their respective threads.
    for agent_id, text in completed_by_agent.items():
        thread = sess.chat_threads.setdefault(agent_id, [])
        thread.append({"role": "assistant", "agent_id": agent_id, "text": text, "ts": time.time()})
    thread_all.append({
        "role": "assistant",
        "agent_id": "all",
        "text": completed_by_agent.get("CHAIR", ""),
        "ts": time.time(),
    })


def _thread_to_messages(thread: list[dict], final_user: str) -> list[dict]:
    """Convert a thread history into Anthropic messages, appending the pending user turn."""
    msgs: list[dict] = []
    for entry in thread[:-1]:  # skip the last (just-appended user message)
        if entry["role"] == "user":
            msgs.append({"role": "user", "content": entry["text"]})
        else:
            msgs.append({"role": "assistant", "content": entry["text"]})
    msgs.append({"role": "user", "content": final_user})
    return msgs
