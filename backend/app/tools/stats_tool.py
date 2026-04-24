"""Local-compute tools: bootstrap, power_calc, sympy_simplify.

These are fast and safe (no network, no user code). Real reviewers' snippets
use sandbox_run. These are convenience primitives that appear often in traces.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import stats as spstats
import sympy


def bootstrap(data: list[float], B: int = 2000) -> dict:
    arr = np.asarray(data, dtype=float)
    if arr.size < 3:
        return {"ok": False, "error": "need at least 3 observations"}
    rng = np.random.default_rng(42)
    means = rng.choice(arr, size=(B, arr.size), replace=True).mean(axis=1)
    ci_low, ci_high = np.percentile(means, [2.5, 97.5])
    return {
        "ok": True,
        "mean": float(arr.mean()),
        "std": float(arr.std(ddof=1)),
        "ci95": [float(ci_low), float(ci_high)],
        "B": B,
    }


def power_calc(delta: float, alpha: float = 0.05, beta: float = 0.20) -> dict:
    """Required n per group for a two-sample t-test at effect size delta (in sigma).
    Uses the normal-approximation formula:
        n = 2 * ((z_{1-α/2} + z_{1-β}) / δ)^2
    """
    if delta <= 0:
        return {"ok": False, "error": "delta must be > 0"}
    z_alpha = spstats.norm.ppf(1 - alpha / 2)
    z_beta = spstats.norm.ppf(1 - beta)
    n = 2.0 * ((z_alpha + z_beta) / delta) ** 2
    n_ceil = int(math.ceil(n))
    return {"ok": True, "n_per_group": n_ceil, "total": n_ceil * 2, "delta": delta, "alpha": alpha, "beta": beta}


def sympy_simplify(expr: str) -> dict:
    try:
        parsed = sympy.sympify(expr)
        simplified = sympy.simplify(parsed)
        return {"ok": True, "input": expr, "simplified": str(simplified)}
    except (sympy.SympifyError, SyntaxError, TypeError, ValueError) as e:
        return {"ok": False, "error": f"could not parse: {e}"}
