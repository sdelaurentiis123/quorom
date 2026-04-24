"""Timer-driven mock session runner.

Emits the exact SSE event shapes the real runner will. Lets us build and
verify the entire frontend pipeline before the LLM integration lands.
Swapped out in M9 for the real session_runner.
"""
from __future__ import annotations

import asyncio
import logging

from .sessions import Session
from .types import PERSONAS, SENIORS

log = logging.getLogger("quorum.mock")

_DEMO_PAPER = {
    "id": "2604.01188",
    "title": "Emergent Calibration in Mid-Scale Transformers",
    "authors": "L. Okafor, R. Hase, M. Ibáñez",
    "venue": "arXiv · preprint · Apr 2026",
    "abstract": (
        "We report that calibration error on held-out reasoning benchmarks drops "
        "discontinuously between 2.8B and 6.7B parameters, and argue this transition "
        "is driven by a phase change in attention entropy rather than by additional "
        "training tokens."
    ),
    "sections": [
        {"id": "§1", "title": "Introduction"},
        {"id": "§2", "title": "Related work"},
        {"id": "§3", "title": "Method"},
        {"id": "§4", "title": "Results"},
        {"id": "§5", "title": "Discussion"},
    ],
}

_DEMO_TRACES = {
    "METH": [
        ("read", "read §3 method; note matched-compute claim"),
        ("tool", "$ arxiv.search(\"ablation fig.4 layer-wise\") → 3 hits"),
        ("think", "§4.2 varies heads AND depth simultaneously"),
        ("tool", "$ sandbox.run(\"repro/abl_small.py\", seed=[0..4])"),
        ("flag", "ablation not single-axis; effect unattributable"),
        ("commit", "finding committed · severity: HIGH"),
    ],
    "STAT": [
        ("read", "read §4 results; locate fig. 3 caption"),
        ("think", "fig. 3: n=48 held-out prompts — suspicious"),
        ("tool", "$ power_calc(δ=0.7σ, α=0.05, β=0.20) → n≥112"),
        ("tool", "$ bootstrap(results.csv, B=10000)"),
        ("flag", "headline claim underspecified statistically"),
        ("commit", "finding committed · severity: HIGH"),
    ],
    "THRY": [
        ("read", "read §3.2; derivation of eq. (3)"),
        ("think", "scaling exponent assumes A2 holds"),
        ("tool", "$ sympy.simplify(loss_bound)"),
        ("flag", "mechanism claim unsupported in target regime"),
        ("commit", "finding committed · severity: MED"),
    ],
    "EMPR": [
        ("tool", "$ arxiv.search(\"HELM-μ calibration 2023..2026\")"),
        ("read", "cross-ref with Kaplan'24, Chen'25"),
        ("flag", "baseline omission is not acknowledged"),
        ("commit", "finding committed · severity: MED"),
    ],
    "STLM": [
        ("read", "read §1 claims carefully"),
        ("think", "charitable: effect IS robust at scale"),
        ("commit", "proposed rewrite attached · severity: NOTE"),
    ],
}

_DEMO_FINDINGS = {
    "METH": {"id": "METH-1", "sev": "high", "rank": 2, "title": "Ablation in §4.2 is not single-axis",
             "text": "Fig. 4 varies both head count and depth simultaneously; the effect cannot be attributed to either axis.",
             "section": "§4.2", "cites": ["fig.4", "tab.2"]},
    "STAT": {"id": "STAT-1", "sev": "high", "rank": 1, "title": "Headline effect is statistically underspecified",
             "text": "Fig. 3 reports an effect at n=48 held-out prompts; power analysis suggests n≥112 is required for α=.05 at the reported effect size.",
             "section": "§4", "cites": ["fig.3", "§4.1"]},
    "THRY": {"id": "THRY-1", "sev": "med", "rank": 3, "title": "Assumption A2 silently breaks in target regime",
             "text": "The scaling derivation rests on A2, which does not hold for d>1024 — exactly the regime the paper focuses on.",
             "section": "§3.2", "cites": ["eq.(3)", "app.B"]},
    "EMPR": {"id": "EMPR-1", "sev": "med", "rank": 4, "title": "Stronger prior baseline is omitted",
             "text": "Kaplan'24 reports superior HELM-μ calibration on comparable models. The paper does not cite or compare against it.",
             "section": "§2", "cites": ["Kaplan'24"]},
    "STLM":{"id": "STLM-1", "sev": "note", "rank": 6, "title": "Charitable rewrite of claim C1",
             "text": "A directional (rather than measured-effect) framing of the headline claim would survive STAT-1 with only minor rephrasing in §1.",
             "section": "§1", "cites": ["§1.2"]},
}

_DEMO_MIN_EXP = {
    "title": "Repro fig.3 at n≥112 with single-axis ablation",
    "resolves": ["STAT-1", "METH-1"],
    "cost": {"gpu_hours": 48.0, "gpu_type": "A100-80G", "eval_sweeps": 2},
    "yaml": (
        "experiment:\n"
        "  name: calibration_repro_n112\n"
        "  objective: validate headline fig.3 effect at adequate sample size\n"
        "  resolves: [STAT-1, METH-1]\n"
        "  model:\n"
        "    family: decoder-only\n"
        "    params: 2_800_000_000\n"
        "  data:\n"
        "    eval_set: HELM-μ reasoning\n"
        "    n: 112\n"
        "  training:\n"
        "    seeds: 3\n"
        "    hours_est: 48.0\n"
        "  acceptance_criteria:\n"
        "    - |mean_effect| ≥ 0.7σ with 95% CI excluding 0\n"
        "    - single-axis ablation: head_count held fixed\n"
    ),
}


async def run_mock_session(sess: Session) -> None:
    """Drive the full 5-phase state machine via timed SSE events."""
    bus = sess.bus
    try:
        # --- intake ---
        bus.publish({"type": "phase.change", "phase": "intake"})
        await asyncio.sleep(0.8)
        sess.paper = _DEMO_PAPER
        bus.publish({"type": "paper.extracted", "paper": _DEMO_PAPER})
        await asyncio.sleep(0.6)

        # --- reading: vectors identified one by one ---
        bus.publish({"type": "phase.change", "phase": "reading"})
        for p in PERSONAS:
            await asyncio.sleep(0.6)
            vector = {"agent_id": p["id"], "angle": p["angle"]}
            sess.vectors.append(vector)
            bus.publish({"type": "vector.identified", **vector})

        # --- deliberation: all 6 parallel, streaming traces ---
        bus.publish({"type": "phase.change", "phase": "deliberation"})
        await asyncio.gather(*[_mock_reviewer(sess, p["id"]) for p in PERSONAS])

        # --- converging: 3 seniors sequentially ---
        bus.publish({"type": "phase.change", "phase": "converging"})
        for s in SENIORS:
            bus.publish({"type": "senior.start", "senior_id": s["id"]})
            for p in [0.2, 0.4, 0.6, 0.8, 1.0]:
                await asyncio.sleep(0.25)
                bus.publish({"type": "senior.progress", "senior_id": s["id"], "p": p})
            bus.publish({"type": "senior.signed", "senior_id": s["id"]})

        # --- verdict ---
        bus.publish({"type": "phase.change", "phase": "verdict"})
        ranked = sorted(_DEMO_FINDINGS.values(), key=lambda f: f["rank"])
        sess.findings = ranked
        sess.verdict = {"ranked": ranked, "min_experiment": _DEMO_MIN_EXP}
        bus.publish({"type": "verdict.ready", "ranked": ranked, "min_experiment": _DEMO_MIN_EXP})

    except asyncio.CancelledError:
        log.info("mock session %s cancelled", sess.id)
        bus.publish({"type": "error", "where": "cancelled", "message": "session cancelled"})
        raise
    except Exception as e:  # pragma: no cover
        log.exception("mock session %s failed", sess.id)
        bus.publish({"type": "error", "where": "mock_runner", "message": str(e)})
    finally:
        bus.close()


async def _mock_reviewer(sess: Session, persona_id: str) -> None:
    bus = sess.bus
    try:
        bus.publish({"type": "agent.start", "agent_id": persona_id})
        traces = _DEMO_TRACES[persona_id]
        # Stagger per-agent so they don't all finish in lockstep.
        jitter_map = {"METH": 0.0, "STAT": 0.15, "THRY": 0.1, "EMPR": 0.25, "HIST": 0.3, "STLM": 0.45}
        await asyncio.sleep(jitter_map.get(persona_id, 0.0))
        for i, (kind, text) in enumerate(traces):
            await asyncio.sleep(0.6 + (i * 0.08))
            t = (i + 1) / len(traces)
            bus.publish({
                "type": "agent.trace",
                "agent_id": persona_id,
                "trace": {"t": t, "kind": kind, "text": text},
            })
        bus.publish({
            "type": "agent.finding",
            "agent_id": persona_id,
            "finding": _DEMO_FINDINGS[persona_id],
        })
    except asyncio.CancelledError:
        bus.publish({
            "type": "agent.finding",
            "agent_id": persona_id,
            "finding": {
                "id": f"{persona_id}-cancel",
                "sev": "note",
                "rank": 99,
                "title": "Review cancelled",
                "text": "Session was cancelled before this reviewer committed a finding.",
                "section": "—",
                "cites": [],
            },
        })
        raise
