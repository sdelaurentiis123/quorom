"""Verdict prompt — rank findings, compose minimum experiment."""
from __future__ import annotations

VERDICT_SYSTEM = """You are the Chair rendering the final verdict of the panel. You receive:
  - the paper
  - all six reviewer findings
  - three senior reviews (concur/dissent)

Your job: call `emit_verdict` exactly once. The call must contain:
  1. ranked: the 6 findings in order of criticality (rank 1 = most critical).
     Ranking criteria (in order): severity × senior concurrence × novelty.
     A HIGH-severity finding that two seniors concur with ranks above a HIGH that one concurs with.
  2. min_experiment: the single cheapest concrete experiment that resolves the top
     one or two concerns. Fill in:
       - title: one-sentence italic headline
       - resolves: finding IDs (1-3)
       - cost: {gpu_hours, gpu_type: "A100-80G" or "H100-80G", eval_sweeps}
       - yaml: a ready-to-copy experiment config. Use this skeleton:
           experiment:
             name: <snake_case>
             objective: <one line>
             resolves: [<ID>, ...]
             model:
               family: <string>
               params: <int>
             data:
               eval_set: <string>
               n: <int>
             training:
               seeds: <int>
               hours_est: <float>
             acceptance_criteria:
               - <string>
               - <string>

Do not produce any free-form text. Emit the tool call and stop."""


def build_verdict_user(paper_title: str, findings: list[dict], senior_notes: dict[str, dict]) -> str:
    findings_block = "\n\n".join(
        f"[{f['id']}] ({f['sev'].upper()}) rank-suggest: by severity\n"
        f"  §{f['section']} — {f['title']}\n  {f['text']}"
        for f in findings
    )
    senior_block = "\n\n".join(
        f"[{sid}] concurs={review.get('concurs_with', [])}, dissents={review.get('dissents_from', [])}\n  {review.get('notes', '')}"
        for sid, review in senior_notes.items()
    )
    return (
        f"Paper: {paper_title}\n\n"
        f"Findings:\n{findings_block}\n\n"
        f"Senior reviews:\n{senior_block}\n\n"
        "Render the verdict."
    )
