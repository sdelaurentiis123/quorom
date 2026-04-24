"""Dispatch tests — tool routing + unknown tool rejection."""
from __future__ import annotations

import pytest

from app.tools.dispatch import execute_tool


async def _noop_trace(_t: dict) -> None:
    return None


@pytest.mark.asyncio
async def test_unknown_tool_returns_error():
    res = await execute_tool("not_a_tool", {}, _noop_trace)
    assert res["ok"] is False
    assert "unknown" in res["error"].lower()


@pytest.mark.asyncio
async def test_power_calc_routes_through_dispatch():
    res = await execute_tool("power_calc", {"delta": 0.7}, _noop_trace)
    assert res["ok"] is True
    assert 20 <= res["n_per_group"] <= 60


@pytest.mark.asyncio
async def test_bootstrap_routes_through_dispatch():
    res = await execute_tool("bootstrap", {"data": list(range(1, 11)), "B": 300}, _noop_trace)
    assert res["ok"] is True
    assert "ci95" in res
