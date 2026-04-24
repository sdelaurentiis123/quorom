"""Tool JSON schemas for Anthropic's tool-use API.

Rules:
- Tool names use underscores (Anthropic enforces ^[a-zA-Z0-9_-]{1,64}$).
- The UI renders dotted names (e.g. `arxiv.search`) — the on_trace formatter
  does the translation.
- `commit_finding.id` is Literal-constrained to PERSONA_IDS so the LLM cannot
  emit a bogus ID. If it tries, we refuse with is_error and emit a `flag` trace.
"""
from __future__ import annotations

from ..types import PERSONA_IDS

_SEV = ["high", "med", "low", "note"]

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "arxiv_search",
        "description": "Search arXiv. Returns up to k paper records with id + title + abstract.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "arxiv_read",
        "description": "Fetch the full abstract + section summary for a single arXiv paper by id.",
        "input_schema": {
            "type": "object",
            "properties": {"arxiv_id": {"type": "string"}},
            "required": ["arxiv_id"],
        },
    },
    {
        "name": "s2_neighbors",
        "description": "Semantic Scholar: find papers citing or cited by an arXiv paper.",
        "input_schema": {
            "type": "object",
            "properties": {
                "arxiv_id": {"type": "string"},
                "direction": {"type": "string", "enum": ["cites", "cited_by"], "default": "cited_by"},
                "k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
            },
            "required": ["arxiv_id"],
        },
    },
    {
        "name": "bootstrap",
        "description": "Bootstrap a 95% CI for the mean of an observation vector.",
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "array", "items": {"type": "number"}},
                "B": {"type": "integer", "default": 2000, "minimum": 200, "maximum": 20000},
            },
            "required": ["data"],
        },
    },
    {
        "name": "power_calc",
        "description": "Required sample size for a two-sample t-test at delta/sigma, alpha, beta.",
        "input_schema": {
            "type": "object",
            "properties": {
                "delta": {"type": "number", "description": "effect size in sigma units"},
                "alpha": {"type": "number", "default": 0.05},
                "beta":  {"type": "number", "default": 0.20},
            },
            "required": ["delta"],
        },
    },
    {
        "name": "sympy_simplify",
        "description": "Simplify a symbolic expression via sympy. Returns simplified string.",
        "input_schema": {
            "type": "object",
            "properties": {"expr": {"type": "string"}},
            "required": ["expr"],
        },
    },
    {
        "name": "sandbox_run",
        "description": (
            "Run a short Python snippet in an isolated sandbox (Docker, no network). "
            "Use for statistical checks, quick reproductions, or symbolic math. "
            "Available libraries: numpy, scipy, pandas, sympy, statsmodels. "
            "Print results to stdout."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source"},
                "timeout_s": {"type": "integer", "default": 20, "minimum": 1, "maximum": 30},
            },
            "required": ["code"],
        },
    },
    {
        "name": "flag",
        "description": "Raise an intermediate observation. Use for surfacing a concern before you commit a final finding.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "one-line note"}},
            "required": ["text"],
        },
    },
    {
        "name": "commit_finding",
        "description": (
            "Commit your final structured finding. Call this exactly once at the end of your investigation. "
            "After this call, your turn ends."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id":      {"type": "string", "enum": list(PERSONA_IDS), "description": "Your persona ID; must match the one given to you."},
                "sev":     {"type": "string", "enum": _SEV},
                "title":   {"type": "string", "description": "one-line italic headline"},
                "text":    {"type": "string", "description": "2-3 sentence finding body"},
                "section": {"type": "string", "description": "paper section ref, e.g. §4.2"},
                "cites":   {"type": "array", "items": {"type": "string"}, "default": []},
            },
            "required": ["id", "sev", "title", "text", "section"],
        },
    },
]

# Orchestrator has a smaller surface: emit sections + vectors.
ORCHESTRATOR_TOOLS: list[dict] = [
    {
        "name": "emit_vector",
        "description": "Emit one identified attack vector. Call once per reviewer you want to convene.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "enum": list(PERSONA_IDS)},
                "angle":    {"type": "string", "description": "one-sentence concrete claim under attack"},
            },
            "required": ["agent_id", "angle"],
        },
    },
]

# Senior panel: light research surface.
SENIOR_TOOLS: list[dict] = [
    TOOL_SCHEMAS[0],  # arxiv_search
    TOOL_SCHEMAS[2],  # s2_neighbors
    {
        "name": "commit_senior_review",
        "description": "Commit your senior review. Call exactly once at the end.",
        "input_schema": {
            "type": "object",
            "properties": {
                "concurs_with":   {"type": "array", "items": {"type": "string"}, "description": "finding IDs the senior concurs with"},
                "dissents_from":  {"type": "array", "items": {"type": "string"}, "description": "finding IDs the senior disagrees with"},
                "notes":          {"type": "string", "description": "one paragraph summary"},
            },
            "required": ["notes"],
        },
    },
]

# Verdict: one tool to emit the final structured verdict.
VERDICT_TOOLS: list[dict] = [
    {
        "name": "emit_verdict",
        "description": "Emit the final ranked verdict + minimum experiment. Call exactly once.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ranked": {
                    "type": "array",
                    "description": "Findings in rank order (1 = most critical).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "sev": {"type": "string", "enum": _SEV},
                            "rank": {"type": "integer"},
                            "title": {"type": "string"},
                            "text": {"type": "string"},
                            "section": {"type": "string"},
                            "cites": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["id", "sev", "rank", "title", "text", "section"],
                    },
                },
                "min_experiment": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "resolves": {"type": "array", "items": {"type": "string"}},
                        "cost": {
                            "type": "object",
                            "properties": {
                                "gpu_hours": {"type": "number"},
                                "gpu_type": {"type": "string"},
                                "eval_sweeps": {"type": "integer"},
                            },
                            "required": ["gpu_hours", "gpu_type", "eval_sweeps"],
                        },
                        "yaml": {"type": "string", "description": "ready-to-copy experiment config"},
                    },
                    "required": ["title", "resolves", "cost", "yaml"],
                },
            },
            "required": ["ranked", "min_experiment"],
        },
    },
]
