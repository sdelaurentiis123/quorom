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
        await client.messages.create(
            model=model,
            max_tokens=1,
            system=system_blocks,
            messages=[{"role": "user", "content": "warm"}],
        )
        log.info("prompt cache warmed")
    except Exception as e:
        log.warning("prompt cache warmup failed (non-fatal): %s", e)
