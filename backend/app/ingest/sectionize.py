"""Section extraction — regex first, Haiku fallback.

The orchestrator delegates to this so section refs in findings always
match a real anchor in the paper. Regex handles ~70% of arXiv PDFs;
if we get <3 sections, fall back to a small Haiku call.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .. import config
from ..llm.client import get_client

log = logging.getLogger("quorum.sectionize")

_HEADING_RE = re.compile(
    r"^(?P<num>\d+(?:\.\d+)?)\s+(?P<title>[A-Z][A-Za-z][A-Za-z0-9 ,\-:]{1,60})\s*$",
    re.MULTILINE,
)


def regex_sections(text: str) -> list[dict[str, str]]:
    seen = set()
    out: list[dict[str, str]] = []
    for m in _HEADING_RE.finditer(text):
        num = m.group("num")
        title = m.group("title").strip()
        if num in seen:
            continue
        seen.add(num)
        out.append({"id": f"§{num}", "title": title})
    return out


async def llm_fallback_sections(text: str) -> list[dict[str, str]]:
    client = get_client()
    # Send only the first ~20k characters — headings cluster at the top.
    snippet = text[:20_000]
    prompt = (
        "Extract the numbered section headings from this paper. Return JSON array "
        'of objects `{"id": "§N", "title": "..."}` in reading order. '
        "Only top-level and first-level subsection headings (§1, §1.1, §2, etc.). "
        "Return a JSON array and nothing else.\n\n"
        f"<paper>\n{snippet}\n</paper>"
    )
    try:
        resp = await client.messages.create(
            model=config.MODEL_SECTIONIZE_FALLBACK,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        text_out = "".join(
            (b.text if hasattr(b, "text") else "") for b in resp.content
        )
        parsed = _parse_json_array(text_out)
        return [s for s in parsed if isinstance(s, dict) and "id" in s and "title" in s]
    except Exception as e:
        log.warning("sectionize fallback failed: %s", e)
        return []


def _parse_json_array(s: str) -> list[Any]:
    m = re.search(r"\[.*\]", s, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return []


async def sectionize(text: str) -> list[dict[str, str]]:
    sections = regex_sections(text)
    if len(sections) >= 3:
        return sections
    return await llm_fallback_sections(text)


def preview(sections: list[dict[str, str]]) -> str:
    return "\n".join(f"  {s['id']}  {s['title']}" for s in sections) or "(no sections detected)"
