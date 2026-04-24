"""Tool dispatch + on_trace enrichment.

The stream_loop calls `execute_tool(name, input, on_trace)`. Dispatch maps
the tool name to the concrete implementation, emits a `read`-style trace
for arxiv_read (so users see "read: <paper title>"), and returns a dict
result that stream_loop serializes into the next turn's tool_result block.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from . import arxiv_tool, s2_tool, stats_tool, sandbox_tool


async def _maybe_await(v: Any) -> None:
    if hasattr(v, "__await__"):
        await v


async def execute_tool(
    name: str,
    inp: dict,
    on_trace: Callable[[dict], Awaitable[None] | None],
) -> dict:
    try:
        if name == "arxiv_search":
            return await arxiv_tool.arxiv_search(inp.get("query", ""), inp.get("k", 5))

        if name == "arxiv_read":
            res = await arxiv_tool.arxiv_read(inp.get("arxiv_id", ""))
            if res.get("ok"):
                title = (res.get("title") or "")[:60]
                await _maybe_await(on_trace({"kind": "read", "text": f"read arXiv:{res.get('id','?')} — {title}"}))
            return res

        if name == "s2_neighbors":
            return await s2_tool.s2_neighbors(
                arxiv_id=inp.get("arxiv_id", ""),
                direction=inp.get("direction", "cited_by"),
                k=inp.get("k", 5),
            )

        if name == "bootstrap":
            return stats_tool.bootstrap(inp.get("data", []), inp.get("B", 2000))

        if name == "power_calc":
            return stats_tool.power_calc(
                delta=float(inp.get("delta", 0)),
                alpha=float(inp.get("alpha", 0.05)),
                beta=float(inp.get("beta", 0.20)),
            )

        if name == "sympy_simplify":
            return stats_tool.sympy_simplify(inp.get("expr", ""))

        if name == "sandbox_run":
            return await sandbox_tool.sandbox_run(
                inp.get("code", ""),
                int(inp.get("timeout_s", 20)),
            )

        return {"ok": False, "error": f"unknown tool: {name}"}
    except Exception as e:  # pragma: no cover
        return {"ok": False, "error": f"tool {name} raised: {e}"}
