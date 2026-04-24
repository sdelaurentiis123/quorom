"""Local-compute tool tests."""
from __future__ import annotations

from app.tools.stats_tool import bootstrap, power_calc, sympy_simplify


def test_bootstrap_returns_ci():
    data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    res = bootstrap(data, B=500)
    assert res["ok"] is True
    assert 4.0 < res["mean"] < 7.0
    assert res["ci95"][0] < res["mean"] < res["ci95"][1]


def test_bootstrap_rejects_tiny_sample():
    res = bootstrap([1.0, 2.0])
    assert res["ok"] is False


def test_power_calc_sensible():
    res = power_calc(delta=0.7, alpha=0.05, beta=0.20)
    assert res["ok"] is True
    # Standard formula gives ~32 per group; double-checked against R's pwr.t.test.
    assert 25 <= res["n_per_group"] <= 50


def test_power_calc_rejects_non_positive_delta():
    assert power_calc(delta=0)["ok"] is False


def test_sympy_simplify_basic():
    res = sympy_simplify("sin(x)**2 + cos(x)**2")
    assert res["ok"] is True
    assert res["simplified"] == "1"


def test_sympy_simplify_rejects_garbage():
    res = sympy_simplify("definitely not an expression !!!")
    assert res["ok"] is False
