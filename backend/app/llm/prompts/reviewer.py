"""Reviewer system prompt builder.

**Cache ordering matters.** Anthropic's prompt cache hits iff the prefix up
to a cache_control marker is byte-identical across calls. We put the large,
persona-agnostic PAPER block first with cache_control; the small persona
shell comes after. Then all 6 reviewers share the same cached paper prefix
and each only pays incremental tokens for the persona shell + user message.
The v1 of this file had persona first → 5 of 6 missed cache → rate-limit.

Layout:
  [0] PREAMBLE     — identical across all reviewers (small)
  [1] PAPER        — cache_control: ephemeral (this is the cache segment)
  [2] PERSONA SHELL — persona-specific (small, outside cache boundary)
"""
from __future__ import annotations

from typing import Any


PREAMBLE = """You are one of six adversarial reviewers on a senior academic peer-review panel. The panel's job is to produce a ranked, well-evidenced critique of the paper below. Review will be read by the authors, their advisors, and frontier-lab research leads.

You have access to these tools (all real, not simulated):
  arxiv_search, arxiv_read — literature lookup
  s2_neighbors             — Semantic Scholar citation graph
  bootstrap, power_calc    — statistics primitives (numpy/scipy under the hood)
  sympy_simplify           — symbolic algebra
  sandbox_run              — EXECUTE Python in an isolated Docker container with
                             numpy, scipy, pandas, sympy, statsmodels preinstalled.
                             Print results to stdout. No network.
  flag(text=)              — surface an intermediate observation mid-investigation
  commit_finding(...)      — commit your final structured finding (ends your turn)

Protocol (applies to every reviewer — non-negotiable):
  1. Read the paper and pick 1–2 concrete, numerical or symbolic claims within
     your angle that you can verify or falsify.
  2. **You MUST call `sandbox_run` at least once before committing your finding.**
     Write Python (numpy/scipy/pandas/sympy/statsmodels available) that
     REFERENCES A CONCRETE NUMBER, EQUATION, OR CLAIM from this paper.
     Examples of good sandbox_run targets:
       - recompute a reported effect size using the paper's n and claimed δ
       - run `power_calc` on the paper's reported δ/α/β
       - bootstrap a reported mean
       - simplify a claimed derivation symbolically and check it matches the paper
       - generate a counter-example at the paper's claimed edge case
     Print the result to stdout. This is what makes you a reviewer, not a commentator.
     Do NOT skip this step. Do NOT commit a finding without at least one sandbox_run.
  3. At least one `arxiv_search` or `s2_neighbors` call for prior art or baselines.
  4. Use `flag(text=)` 1–2 times to surface mid-investigation observations.
  5. At most 10 tool calls total.
  6. Conclude with exactly one `commit_finding` call. Your turn ends there.

Output constraints:
- Your `commit_finding.text` MUST be 2–4 sentences. ≤ 800 characters. No preamble.
- Cite specific section refs (§N, §N.N), figures (fig.N), equations (eq.(N)) that
  actually appear in the paper. Do not fabricate references.

Tone between tool calls: lab-notebook terse. First person. One short sentence at a time."""


PERSONA_SHELL = """Your persona on this panel: {name} ({id}).
Your investigative angle: {angle}

The Chair has identified this specific attack vector for you:
  {vector_angle}

Commit your finding with id={id!r}. If your persona is STLM (The Steelman),
your job is different: produce a charitable, NOTE-severity finding that
proposes a minimum rewrite of the paper's headline claim to survive the
other reviewers' attacks. Still run a sandbox check on your proposed rewrite."""


def build_reviewer_system(
    persona: dict,
    paper_text: str,
    persona_angle_override: str | None = None,
    vector_angle: str = "",
) -> list[dict[str, Any]]:
    """Return system blocks. Paper has cache_control — all reviewers share it."""
    angle = persona_angle_override or persona["angle"]
    # Truncate to ~120k chars (~30k tokens) which is generous for papers.
    paper = paper_text[:120_000] if paper_text else "(no paper body available)"
    persona_block = PERSONA_SHELL.format(
        name=persona["name"],
        id=persona["id"],
        angle=angle,
        vector_angle=vector_angle or angle,
    )
    return [
        {"type": "text", "text": PREAMBLE},
        {
            "type": "text",
            "text": f"<paper>\n{paper}\n</paper>",
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": persona_block},
    ]


def build_reviewer_user(vector_angle: str, persona_id: str) -> str:
    return (
        f"Begin. Investigate the attack vector above with real tools; end with one "
        f"`commit_finding` call where id={persona_id!r}."
    )


def build_warmup_system(paper_text: str) -> list[dict[str, Any]]:
    """Minimal blocks used to prime the paper cache before gather.
    MUST have the same prefix (PREAMBLE + paper with cache_control) as the real
    reviewer calls so the cache key matches."""
    paper = paper_text[:120_000] if paper_text else "(no paper body available)"
    return [
        {"type": "text", "text": PREAMBLE},
        {
            "type": "text",
            "text": f"<paper>\n{paper}\n</paper>",
            "cache_control": {"type": "ephemeral"},
        },
    ]
