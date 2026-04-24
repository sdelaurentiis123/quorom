"""Tool JSON schemas for Anthropic's tool-use API.

Rules:
- Tool names use underscores (Anthropic enforces ^[a-zA-Z0-9_-]{1,64}$).
- The UI renders dotted names (e.g. `arxiv.search`) — the on_trace formatter
  does the translation.
- `commit_finding.id` is Literal-constrained to PERSONA_IDS so the LLM cannot
  emit a bogus ID. If it tries, we refuse with is_error and emit a `flag` trace.
"""
from __future__ import annotations

from ..types import ORCHESTRATOR_POOL, PERSONA_IDS

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
                "title":   {"type": "string", "maxLength": 140, "description": "one-line italic headline"},
                "text":    {"type": "string", "maxLength": 800, "description": "2-4 sentence finding body. Max ~800 chars. No preamble."},
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
        "description": (
            "Emit one identified attack vector. Call once per reviewer you want to convene. "
            "Include the section IDs most relevant to this attack so the reviewer only reads the "
            "parts of the paper that matter — this is important for rate-limit + focus."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "enum": list(ORCHESTRATOR_POOL),
                             "description": "Pick a seat from the non-STLM pool. STLM is appended automatically."},
                "angle":    {"type": "string", "description": "one-sentence concrete claim under attack, anchored to a section reference"},
                "relevant_sections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Section IDs (e.g. ['§4', '§4.2', '§5']) the reviewer must read. 1-3 sections.",
                    "default": [],
                },
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

# Report composer: one tool that takes the final prose + structured ranking.
REPORT_TOOLS: list[dict] = [
    {
        "name": "emit_report",
        "description": (
            "Emit the final panel verdict report. Call exactly once after you have "
            "composed the complete Markdown document. Your turn ends after this call."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "markdown": {
                    "type": "string",
                    "description": "The full Markdown review report you composed. "
                                   "Must include all required section headings.",
                },
                "ranked_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Finding IDs in rank order (1 = most critical). Must match the "
                                   "order the findings appear in your 'Principal Concerns' section.",
                },
                "recommended_experiment": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "maxLength": 160},
                        "prose": {"type": "string", "maxLength": 1200,
                                  "description": "2-4 sentence prose description of the experiment. No YAML."},
                        "resolves": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "prose", "resolves"],
                },
            },
            "required": ["markdown", "ranked_ids", "recommended_experiment"],
        },
    },
]

# Kept as alias so old imports keep working during the refactor.
VERDICT_TOOLS = REPORT_TOOLS
