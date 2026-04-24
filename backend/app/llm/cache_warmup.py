"""Prime Anthropic's prompt cache before the 6 parallel reviewers launch.

Rationale (from eng-review issue 3): if all 6 reviewers asyncio.gather to
the same system prompt, the first one writes the cache and the other 5
start before it's written, missing. Warming once up front means all 6
subsequent calls hit warm cache. Cost: one `messages.create(max_tokens=1)`
call (~$0.03 for a 20k-token paper). Saves ~$0.50+ across the 6 turns.
"""
from __future__ import annotations

import logging
from typing import Any

from anthropic import AsyncAnthropic

log = logging.getLogger("quorum.warmup")


async def warmup_reviewer_cache(
    client: AsyncAnthropic,
    model: str,
    system_blocks: list[dict[str, Any]],
) -> None:
    try:
        resp = await client.messages.create(
            model=model,
            max_tokens=1,
            system=system_blocks,
            messages=[{"role": "user", "content": "warm"}],
        )
        u = resp.usage
        log.info(
            "cache warmup complete: input=%d  cache_create=%d  cache_read=%d",
            getattr(u, "input_tokens", 0),
            getattr(u, "cache_creation_input_tokens", 0) or 0,
            getattr(u, "cache_read_input_tokens", 0) or 0,
        )
    except Exception as e:
        log.warning("prompt cache warmup failed (non-fatal): %s", e)
