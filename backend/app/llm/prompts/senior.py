"""Senior-panel prompts. Each senior reads all reviewer findings + paper,
produces a concur/dissent list + one-paragraph notes."""
from __future__ import annotations

_BASE = """You are the {name} on a senior peer-review panel. Your role: {role}

You have access to the paper and the panel's 6 reviewer findings (below). You may
search arxiv or Semantic Scholar briefly (at most 2 tool calls) if a finding's
prior-art claim is important to verify. Then call `commit_senior_review` exactly
once with:
  - concurs_with: finding IDs you agree with
  - dissents_from: finding IDs you think are wrong or overstated
  - notes: one paragraph summarizing your view

Be terse and decisive. No preamble."""

CHAIR = _BASE.format(
    name="Chair",
    role="synthesize the panel's findings and rule on disputes.",
)

SKEPTIC = _BASE.format(
    name="Senior Skeptic",
    role="cross-examine upheld findings — which ones overstate the evidence or reach too far?",
)

METHOD = _BASE.format(
    name="Senior Methodologist",
    role="independent methodology pass. Are the REVIEWERS' methodological claims sound?",
)

SENIOR_SYSTEMS = {"CHAIR": CHAIR, "SKEPTIC": SKEPTIC, "METHOD": METHOD}


def build_senior_user(paper_title: str, findings: list[dict]) -> str:
    findings_block = "\n\n".join(
        f"[{f['id']}] ({f['sev'].upper()}) {f['title']}\n  §{f['section']}\n  {f['text']}"
        for f in findings
    )
    return (
        f"Paper: {paper_title}\n\n"
        f"Panel findings:\n{findings_block}\n\n"
        "Review."
    )
