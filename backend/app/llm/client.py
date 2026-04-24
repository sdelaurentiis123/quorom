"""Shared AsyncAnthropic client. Reads the key from config.ANTHROPIC_API_KEY."""
from __future__ import annotations

from anthropic import AsyncAnthropic

from .. import config

_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Put it in quorum/.env or export it."
            )
        _client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client
