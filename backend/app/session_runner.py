"""Top-level coroutine per session. Drives the full 5-phase state machine
end-to-end with real Anthropic calls and real tools. Phase helpers are
inlined (eng-review decision #6).

==============================================================================
                              PHASE FLOW

    intake     ─► ingest (arxiv or pdf) → paper.extracted (incl. body)
                  sectionize (regex, Haiku fallback)

    reading    ─► orchestrator emits vector.identified* + streams CHAIR traces
                  STLM force-included at end

    deliberation ─► cache warmup (primes shared paper cache)
                    asyncio semaphore-gated gather(reviewers)
                    each reviewer: stream_loop → agent.trace + agent.finding
                    on_trace logs Anthropic usage (cache_read vs cache_write)

    converging ─► 3 seniors sequentially, each emits senior.trace
                   senior.signed ONLY fires on actual commit_senior_review

    verdict    ─► rank + compose min_experiment, emits verdict.trace as it
                   streams; verdict.ready on completion
==============================================================================
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from . import config
from .bus import SessionBus
from .ingest import arxiv_ingest, sectionize
from .ingest.arxiv_ingest import IngestError
from .llm.cache_warmup import warmup_reviewer_cache
from .llm.client import get_client
from .llm.prompts import orchestrator as orch_prompt
from .llm.prompts import report as report_prompt
from .llm.prompts import reviewer as rev_prompt
from .llm.prompts import senior as senior_prompt
from .llm.stream_loop import default_validate_commit_finding, run_agent_loop
from .llm.tools_schema import (
    ORCHESTRATOR_TOOLS,
    REPORT_TOOLS,
    SENIOR_TOOLS,
    TOOL_SCHEMAS,
)
from .sessions import Session
from .tools.dispatch import execute_tool
from .types import MAX_REVIEWERS_NON_STLM, ORCHESTRATOR_POOL, PERSONAS, PERSONA_IDS, SENIORS

log = logging.getLogger("quorum.session_runner")


async def run_session(sess: Session) -> None:
    """Top-level — called via asyncio.create_task from POST /api/sessions."""
    bus = sess.bus
    t0 = time.monotonic()

    def _phase_log(phase: str) -> None:
        log.info("session %s → phase %s (t+%.1fs)", sess.id, phase, time.monotonic() - t0)

    try:
        # ───────── INTAKE ─────────
        _phase_log("intake")
        bus.publish({"type": "phase.change", "phase": "intake"})
        source = sess.source or {}
        try:
            paper, body_text, pdf_bytes = await _ingest(source)
        except IngestError as e:
            log.warning("ingest failed for %s: %s", sess.id, e)
            bus.publish({"type": "error", "where": "intake", "message": str(e)})
            return

        log.info("ingested %s (%d chars body, fmt=%s, pdf=%d bytes)",
                 paper.get("id"), len(body_text), paper.get("body_format"), len(pdf_bytes) if pdf_bytes else 0)
        sections = await sectionize.sectionize(body_text)
        paper["sections"] = sections
        paper["has_pdf"] = bool(pdf_bytes)
        sess.paper = paper
        sess.paper_pdf_bytes = pdf_bytes
        bus.publish({"type": "paper.extracted", "paper": paper})

        # ───────── READING ─────────
        _phase_log("reading")
        bus.publish({"type": "phase.change", "phase": "reading"})
        vectors = await _reading(body_text, sections, bus)
        sess.vectors = vectors

        # ───────── DELIBERATION ─────────
        _phase_log("deliberation")
        bus.publish({"type": "phase.change", "phase": "deliberation"})
        findings = await _deliberation(paper, body_text, vectors, bus)
        sess.findings = findings

        # ───────── CONVERGING ─────────
        _phase_log("converging")
        bus.publish({"type": "phase.change", "phase": "converging"})
        senior_notes = await _converging(paper, findings, bus)
        sess.senior_notes = senior_notes

        # ───────── VERDICT ─────────
        _phase_log("verdict")
        bus.publish({"type": "phase.change", "phase": "verdict"})
        verdict = await _verdict(paper, findings, senior_notes, bus)
        if verdict is not None:
            sess.verdict = verdict
            # Generate the academic-panel-report PDF from the prose markdown
            # BEFORE publishing verdict.ready, so the iframe has bytes to serve
            # the moment the tab flips.
            try:
                from .verdict_pdf import generate_verdict_pdf
                committed_ids = [f.get("id", "").split("-")[0] for f in findings if f.get("id")]
                pdf_bytes = generate_verdict_pdf(
                    paper=paper,
                    report_markdown=verdict.get("report_markdown") or "",
                    session_id=sess.id,
                    committed_agent_ids=[cid for cid in committed_ids if cid],
                )
                sess.verdict_pdf_bytes = pdf_bytes
                log.info("verdict PDF generated: %d bytes (markdown=%d chars)",
                         len(pdf_bytes), len(verdict.get("report_markdown") or ""))
            except Exception as e:  # pragma: no cover
                log.exception("verdict PDF generation failed: %s", e)
            # Publish verdict.ready with prose payload only.
            bus.publish({
                "type": "verdict.ready",
                "ranked": verdict.get("ranked") or [],
                "recommended_experiment": verdict.get("recommended_experiment") or _fallback_recommended_experiment(findings),
                "report_markdown": verdict.get("report_markdown") or "",
            })
        log.info("session %s complete (t+%.1fs)", sess.id, time.monotonic() - t0)

    except asyncio.CancelledError:
        log.info("session %s cancelled", sess.id)
        bus.publish({"type": "error", "where": "cancelled", "message": "session cancelled"})
        raise
    except Exception as e:  # pragma: no cover
        log.exception("session %s failed", sess.id)
        bus.publish({"type": "error", "where": "session_runner", "message": str(e)[:200]})
    finally:
        bus.close()


# ───────────────────────────────────────────────────────────────────────
# ingest
# ───────────────────────────────────────────────────────────────────────

async def _ingest(source: dict[str, Any]) -> tuple[dict, str, bytes | None]:
    kind = source.get("kind")
    if kind == "arxiv":
        return await arxiv_ingest.fetch_arxiv(source["id"])
    if kind == "pdf":
        from .routes.sessions import get_upload
        data = get_upload(source["upload_id"])
        if not data:
            raise IngestError("upload expired or unknown")
        from .ingest import pdf_ingest as pdf_mod
        body, fmt = pdf_mod.extract_markdown(data)
        paper = {
            "id": source["upload_id"][:8],
            "title": _guess_title(body),
            "authors": "(uploaded PDF)",
            "venue": "PDF upload",
            "abstract": (body[:1200].replace("\n", " "))[:800],
            "sections": [],
            "body": body[:60_000],
            "body_format": fmt,
            "has_pdf": True,
        }
        return paper, body, data
    if kind == "demo":
        return await arxiv_ingest.fetch_arxiv("2604.01188")
    raise IngestError(f"unknown source kind: {kind!r}")


def _guess_title(body: str) -> str:
    for line in body.splitlines():
        line = line.strip().lstrip("#").strip()
        if 10 <= len(line) <= 140 and not line.isupper():
            return line
    return "(untitled paper)"


# ───────────────────────────────────────────────────────────────────────
# reading — orchestrator picks vectors + streams CHAIR traces
# ───────────────────────────────────────────────────────────────────────

async def _reading(body_text: str, sections: list[dict], bus: SessionBus) -> list[dict]:
    client = get_client()
    sections_preview = sectionize.preview(sections)

    emitted: list[dict] = []

    async def orch_on_trace(trace: dict) -> None:
        # Orchestrator shows up in the UI as the CHAIR stream.
        bus.publish({
            "type": "chair.trace",
            "trace": {
                "t": 0.5,
                "kind": trace.get("kind", "think"),
                "text": trace.get("text", "")[:120],
            },
        })

    async def orch_dispatch(name: str, inp: dict, _on_trace) -> dict:
        if name == "emit_vector":
            agent_id = inp.get("agent_id")
            angle = inp.get("angle", "")
            if agent_id not in ORCHESTRATOR_POOL:
                return {"ok": False, "error": f"{agent_id!r} is not in the orchestrator pool {ORCHESTRATOR_POOL}"}
            if len([v for v in emitted if v["agent_id"] != "STLM"]) >= MAX_REVIEWERS_NON_STLM:
                # Hard cap — tell the model to stop.
                return {"ok": False, "error": f"panel is full: {MAX_REVIEWERS_NON_STLM} non-STLM reviewers already convened"}
            if any(v["agent_id"] == agent_id for v in emitted):
                return {"ok": False, "error": f"{agent_id} already convened"}
            vector = {"agent_id": agent_id, "angle": angle}
            emitted.append(vector)
            bus.publish({"type": "vector.identified", **vector})
            bus.publish({
                "type": "chair.trace",
                "trace": {"t": 0.5, "kind": "flag", "text": f"convene {agent_id}: {angle[:60]}"},
            })
            return {"ok": True}
        return {"ok": False, "error": f"unknown tool {name}"}

    bus.publish({"type": "chair.trace", "trace": {"t": 0.05, "kind": "read", "text": f"reading paper ({len(body_text)} chars, {len(sections)} sections)"}})

    await run_agent_loop(
        client=client,
        model=config.MODEL_ORCHESTRATOR,
        system=orch_prompt.ORCHESTRATOR_SYSTEM,
        user_msg=orch_prompt.build_orchestrator_user(body_text, sections_preview),
        tools=ORCHESTRATOR_TOOLS,
        on_trace=orch_on_trace,
        dispatch_tool=orch_dispatch,
        commit_tool_name="__never__",
        max_turns=3,
        max_tokens=config.ORCHESTRATOR_MAX_TOKENS,
    )

    if not any(v["agent_id"] == "STLM" for v in emitted):
        stlm = next(p for p in PERSONAS if p["id"] == "STLM")
        vector = {"agent_id": "STLM", "angle": stlm["angle"]}
        emitted.append(vector)
        bus.publish({"type": "vector.identified", **vector})
        bus.publish({
            "type": "chair.trace",
            "trace": {"t": 0.95, "kind": "flag", "text": "convene STLM (charitable seat, always included)"},
        })

    bus.publish({"type": "chair.trace", "trace": {"t": 1.0, "kind": "commit", "text": f"panel convened: {len(emitted)} reviewers"}})
    return emitted


# ───────────────────────────────────────────────────────────────────────
# deliberation — reviewers semaphore-gated, cache-primed
# ───────────────────────────────────────────────────────────────────────

async def _deliberation(paper: dict, body_text: str, vectors: list[dict], bus: SessionBus) -> list[dict]:
    client = get_client()

    # Warmup uses the SAME prefix (preamble + paper) as real reviewer calls so
    # the cache hash matches. Without this, only the first-firing reviewer
    # writes the cache; all others race past it and miss.
    warmup_blocks = rev_prompt.build_warmup_system(body_text)
    await warmup_reviewer_cache(client, config.MODEL_REVIEWER, warmup_blocks)

    vector_by_id = {v["agent_id"]: v for v in vectors}
    sem = asyncio.Semaphore(config.REVIEWER_PARALLEL)

    async def run_one(persona: dict) -> dict | None:
        pid = persona["id"]
        v = vector_by_id.get(pid)
        if not v:
            return None

        async with sem:
            bus.publish({"type": "agent.start", "agent_id": pid})
            traces_emitted = 0

            async def on_trace(trace: dict) -> None:
                nonlocal traces_emitted
                traces_emitted += 1
                t = 1 - 0.93 ** traces_emitted
                bus.publish({
                    "type": "agent.trace",
                    "agent_id": pid,
                    "trace": {"t": t, "kind": trace.get("kind", "think"), "text": trace.get("text", "")[:120]},
                })

            async def dispatch(name: str, inp: dict, _on_trace) -> dict:
                return await execute_tool(name, inp, _on_trace)

            system_blocks = rev_prompt.build_reviewer_system(
                persona=persona,
                paper_text=body_text,
                persona_angle_override=v["angle"],
                vector_angle=v["angle"],
            )

            try:
                finding = await run_agent_loop(
                    client=client,
                    model=config.MODEL_REVIEWER,
                    system=system_blocks,
                    user_msg=rev_prompt.build_reviewer_user(v["angle"], pid),
                    tools=TOOL_SCHEMAS,
                    on_trace=on_trace,
                    dispatch_tool=dispatch,
                    commit_tool_name="commit_finding",
                    validate_commit=default_validate_commit_finding,
                    max_turns=config.REVIEWER_MAX_TURNS,
                    max_tokens=config.REVIEWER_MAX_TOKENS,
                )
            except asyncio.CancelledError:
                bus.publish({
                    "type": "agent.finding", "agent_id": pid,
                    "finding": _placeholder_finding(pid, "cancelled", "Session cancelled."),
                })
                raise

            if finding is None:
                finding = _placeholder_finding(pid, "timeout", "Reviewer exhausted turns without committing.")
            # Normalize the finding shape before it hits the wire. The tool
            # schema says cites is an array of strings but the model sometimes
            # returns a string, null, or omits it — we coerce to list[str]
            # so the frontend never has to defend against it.
            finding["cites"] = _as_str_list(finding.get("cites"))
            finding["id"] = finding.get("id") or f"{pid}-1"
            if not finding["id"].startswith(pid + "-"):
                finding["id"] = f"{pid}-1"
            finding.setdefault("rank", 0)
            finding.setdefault("title", "(no title)")
            finding.setdefault("text", "")
            finding.setdefault("section", "—")
            finding.setdefault("sev", "note")

            bus.publish({"type": "agent.finding", "agent_id": pid, "finding": finding})
            return finding

    active = [p for p in PERSONAS if p["id"] in vector_by_id]
    results = await asyncio.gather(*[run_one(p) for p in active], return_exceptions=True)
    findings = [r for r in results if isinstance(r, dict)]
    sev_order = {"high": 0, "med": 1, "low": 2, "note": 3}
    findings.sort(key=lambda f: sev_order.get(f.get("sev", "note"), 9))
    for i, f in enumerate(findings, start=1):
        f["rank"] = i
    log.info("deliberation complete: %d findings (sev dist: %s)",
             len(findings),
             {k: sum(1 for f in findings if f.get("sev") == k) for k in ("high", "med", "low", "note")})
    return findings


def _placeholder_finding(pid: str, reason: str, text: str) -> dict:
    return {
        "id": f"{pid}-{reason}",
        "sev": "note",
        "rank": 99,
        "title": f"{reason} ({pid})",
        "text": text,
        "section": "—",
        "cites": [],
    }


# ───────────────────────────────────────────────────────────────────────
# converging — 3 seniors sequentially, each streams traces
# senior.signed ONLY fires on real commit_senior_review (fixes prior lie)
# ───────────────────────────────────────────────────────────────────────

async def _converging(paper: dict, findings: list[dict], bus: SessionBus) -> dict[str, dict]:
    client = get_client()
    notes: dict[str, dict] = {}

    for senior in SENIORS:
        sid = senior["id"]
        bus.publish({"type": "senior.start", "senior_id": sid})
        bus.publish({"type": "senior.progress", "senior_id": sid, "p": 0.05})

        committed = False
        trace_count = 0

        async def on_trace(trace: dict, _sid=sid) -> None:
            nonlocal trace_count
            trace_count += 1
            # Bump visible progress off the raw token stream; cap at 0.9 until commit.
            p = min(0.9, 0.1 + trace_count * 0.08)
            bus.publish({"type": "senior.progress", "senior_id": _sid, "p": p})
            bus.publish({
                "type": "senior.trace",
                "senior_id": _sid,
                "trace": {"t": p, "kind": trace.get("kind", "think"), "text": trace.get("text", "")[:120]},
            })

        async def dispatch(name: str, inp: dict, _on_trace) -> dict:
            return await execute_tool(name, inp, _on_trace)

        def validate_senior(inp: dict) -> str | None:
            if "notes" not in inp:
                return "notes required"
            return None

        result = None
        try:
            result = await run_agent_loop(
                client=client,
                model=config.MODEL_SENIOR,
                system=senior_prompt.SENIOR_SYSTEMS[sid],
                user_msg=senior_prompt.build_senior_user(paper["title"], findings),
                tools=SENIOR_TOOLS,
                on_trace=on_trace,
                dispatch_tool=dispatch,
                commit_tool_name="commit_senior_review",
                validate_commit=validate_senior,
                max_turns=5,
                max_tokens=config.SENIOR_MAX_TOKENS,
            )
            if result is not None:
                committed = True
        except asyncio.CancelledError:
            bus.publish({"type": "senior.trace", "senior_id": sid, "trace": {"t": 1.0, "kind": "flag", "text": "cancelled"}})
            raise
        except Exception as e:
            log.warning("senior %s failed: %s", sid, e)
            bus.publish({"type": "senior.trace", "senior_id": sid, "trace": {"t": 1.0, "kind": "flag", "text": f"failed: {str(e)[:72]}"}})

        if committed:
            bus.publish({"type": "senior.progress", "senior_id": sid, "p": 1.0})
            bus.publish({"type": "senior.signed", "senior_id": sid})
        else:
            # Honest: did NOT sign. UI renders this as an inconclusive state.
            bus.publish({"type": "senior.progress", "senior_id": sid, "p": 1.0})
            bus.publish({"type": "senior.inconclusive", "senior_id": sid})

        notes[sid] = result or {"notes": "(senior review unavailable)"}

    return notes


# ───────────────────────────────────────────────────────────────────────
# verdict — compose ranked + min_experiment, streams traces
# ───────────────────────────────────────────────────────────────────────

async def _verdict(paper: dict, findings: list[dict], senior_notes: dict[str, dict], bus: SessionBus) -> dict | None:
    """Compose the panel verdict as prose + structured ranking.

    The report prompt (prompts/report.py) instructs Opus to write a full
    referee-report Markdown document, then call the `emit_report` tool with
    {markdown, ranked_ids, recommended_experiment}. We stream its text_delta
    tokens as `verdict.trace` events so the UI's composing state shows real
    activity throughout the ~60-90s composition.
    """
    client = get_client()
    collected: dict[str, Any] = {}

    async def on_trace(trace: dict) -> None:
        # Stream composer thinking + tool calls into the UI's composing log.
        bus.publish({
            "type": "verdict.trace",
            "trace": {
                "t": 0.5,
                "kind": trace.get("kind", "think"),
                "text": trace.get("text", "")[:160],
            },
        })

    async def dispatch(name: str, inp: dict, _on_trace) -> dict:
        if name == "emit_report":
            md = (inp.get("markdown") or "").strip()
            ranked_ids = inp.get("ranked_ids") or []
            # Re-rank the findings in the order the composer chose.
            by_id = {f.get("id"): f for f in findings}
            ranked = []
            for rid in ranked_ids:
                f = by_id.get(rid)
                if f:
                    f_copy = dict(f)
                    f_copy["rank"] = len(ranked) + 1
                    ranked.append(f_copy)
            # Append any findings the composer forgot to rank, at the end.
            for f in findings:
                if f.get("id") not in {r.get("id") for r in ranked}:
                    f_copy = dict(f)
                    f_copy["rank"] = len(ranked) + 1
                    ranked.append(f_copy)

            rec = inp.get("recommended_experiment") or {}
            if "title" not in rec or "prose" not in rec:
                rec = _fallback_recommended_experiment(findings)
            else:
                rec = {
                    "title": str(rec.get("title") or "(no title)"),
                    "prose": str(rec.get("prose") or ""),
                    "resolves": _as_str_list(rec.get("resolves")),
                }

            collected["report_markdown"] = md
            collected["ranked"] = ranked
            collected["recommended_experiment"] = rec
            await _maybe_await(on_trace({"kind": "commit", "text": f"report committed ({len(md)} chars)"}))
            return {"ok": True}
        return {"ok": False, "error": f"unknown {name}"}

    bus.publish({
        "type": "verdict.trace",
        "trace": {"t": 0.02, "kind": "read",
                  "text": f"composing verdict from {len(findings)} findings + {len(senior_notes or {})} senior notes"},
    })

    await run_agent_loop(
        client=client,
        model=config.MODEL_VERDICT,
        system=report_prompt.REPORT_SYSTEM,
        user_msg=report_prompt.build_report_user(paper, findings, senior_notes),
        tools=REPORT_TOOLS,
        on_trace=on_trace,
        dispatch_tool=dispatch,
        commit_tool_name="__never__",
        max_turns=2,
        max_tokens=config.VERDICT_MAX_TOKENS * 2,  # prose is long
    )

    if not collected:
        log.warning("verdict: composer did not emit_report; using plain fallback")
        collected["report_markdown"] = _fallback_report_markdown(paper, findings, senior_notes)
        collected["ranked"] = sorted(findings, key=lambda f: f.get("rank", 99))
        collected["recommended_experiment"] = _fallback_recommended_experiment(findings)
    return collected


async def _maybe_await(v):
    if hasattr(v, "__await__"):
        await v


def _as_str_list(v) -> list[str]:
    """Coerce a value into list[str]. Accepts list, tuple, string, None."""
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v.strip() else []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if x is not None and str(x).strip()]
    return [str(v)]


def _fallback_recommended_experiment(findings: list[dict]) -> dict:
    top = findings[0] if findings else None
    if not top:
        return {
            "title": "Re-review after revisions",
            "prose": "The panel recommends re-running the review once the authors have addressed the concerns above.",
            "resolves": [],
        }
    return {
        "title": f"Targeted re-run to resolve {top.get('id', '?')}",
        "prose": (
            f"The panel recommends a targeted follow-up experiment focused on "
            f"resolving the highest-priority concern — {top.get('title','')} (§{top.get('section','')}). "
            "Run the minimum ablation that cleanly isolates the contested axis "
            "and report the result with properly-powered statistics. "
            "This should require a modest compute budget on the order of 12–36 A100-hours."
        ),
        "resolves": [top.get("id", "")],
    }


def _fallback_report_markdown(paper: dict, findings: list[dict], _senior_notes: dict) -> str:
    lines = [f"# Executive Summary", ""]
    lines.append(
        f"The Quorum panel reviewed *{paper.get('title','the submitted paper')}*. "
        f"The panel surfaced {len(findings)} material concern(s) spanning methodology, "
        "statistics, and prior art. The composer was unable to produce a full prose report "
        "for this session; please consult the per-concern details below."
    )
    lines.append("")
    lines.append("## Principal Concerns")
    for i, f in enumerate(findings, start=1):
        lines.append("")
        lines.append(f"### {i:02d} — {f.get('title','(no title)')}")
        lines.append("")
        lines.append(
            f"Surfaced by {(f.get('id','') or '').split('-')[0]} in §{f.get('section','?')}: "
            f"{f.get('text','(no detail)')}"
        )
    lines.append("")
    lines.append("## Recommended Next Experiment")
    lines.append("")
    lines.append(
        "See the recommended-experiment card alongside this report for the suggested follow-up."
    )
    return "\n".join(lines)
