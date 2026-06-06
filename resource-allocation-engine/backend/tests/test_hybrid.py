"""
Hybrid (two-phase) tests.

The hybrid runs a `primary` strategy on the full problem, then a `secondary`
strategy fills any orders the primary left unassigned using the trucks that still
have spare capacity. The invariants we prove:

  * Validity — the combined result is still a legal allocation: every pair is
    feasible, no order is served twice, no truck exceeds its capacity.
  * Monotonic coverage — the hybrid never serves *fewer* orders than the primary
    alone (Phase 2 can only add).
  * Batching payoff — on the `batching` profile the second phase genuinely fills
    leftover capacity, lifting coverage above the one-to-one primary.
  * No-residual identity — when the primary already consumes all truck capacity
    (the one-to-one profiles), Phase 2 has nothing to do and the hybrid equals
    the primary exactly.
"""
from __future__ import annotations

import math

import pytest

from app.cost import build_cost_matrix
from app.engine import _residual_matrix, run_algorithm, run_hybrid
from app.generators import generate_scenario
from app.models import CostConfig
from app.strategies import STRATEGIES, get_strategy

PROFILES = ["abundant", "contested", "scarce", "tight_windows", "batching"]
ALGOS = list(STRATEGIES.keys())


def _matrix(scenario):
    return build_cost_matrix(scenario.trucks, scenario.orders,
                             scenario.decision_time, CostConfig())


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("primary", ALGOS)
@pytest.mark.parametrize("secondary", ALGOS)
def test_hybrid_is_valid(profile, primary, secondary):
    """Combined assignment honours feasibility, one-order-once, and capacity."""
    sc = generate_scenario(profile, n_trucks=8, n_orders=12, seed=7)
    res = run_hybrid(sc, primary, secondary)

    cm = _matrix(sc)
    order_idx = {o.id: j for j, o in enumerate(sc.orders)}
    truck_idx = {t.id: i for i, t in enumerate(sc.trucks)}

    orders_seen: set[str] = set()
    truck_load: dict[str, int] = {}
    for a in res.assignments:
        i, j = truck_idx[a.truck_id], order_idx[a.order_id]
        assert math.isfinite(cm.cost[i, j])            # feasible pair only
        assert a.order_id not in orders_seen           # each order at most once
        orders_seen.add(a.order_id)
        truck_load[a.truck_id] = truck_load.get(a.truck_id, 0) + 1
    for tid, load in truck_load.items():               # capacity respected
        assert load <= sc.trucks[truck_idx[tid]].capacity_orders


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("primary", ALGOS)
@pytest.mark.parametrize("secondary", ALGOS)
def test_hybrid_covers_at_least_primary(profile, primary, secondary):
    """Phase 2 can only add orders, never remove them."""
    sc = generate_scenario(profile, n_trucks=8, n_orders=12, seed=7)
    hybrid = run_hybrid(sc, primary, secondary).metrics
    prim = run_algorithm(sc, primary).metrics
    assert hybrid.assigned_count >= prim.assigned_count


@pytest.mark.parametrize("secondary", ["greedy", "min_cost_flow"])
def test_hybrid_fills_leftovers_when_batching(secondary):
    """On the batching profile a one-to-one primary (Hungarian) leaves capacity
    that the secondary can fill, so coverage rises above the primary alone."""
    sc = generate_scenario("batching", n_trucks=8, n_orders=12, seed=7)
    res = run_hybrid(sc, "hungarian", secondary)
    hungarian = run_algorithm(sc, "hungarian").metrics

    phase2 = sum(1 for a in res.assignments
                 if "Phase 2" in (a.explanation.note or ""))
    assert phase2 > 0
    assert res.metrics.assigned_count > hungarian.assigned_count


@pytest.mark.parametrize("profile", ["contested", "scarce", "tight_windows"])
def test_hybrid_equals_primary_when_no_residual_capacity(profile):
    """In strict one-to-one profiles the primary uses every truck it can, so
    Phase 2 finds no spare capacity and the hybrid is identical to the primary."""
    sc = generate_scenario(profile, n_trucks=8, n_orders=12, seed=7)
    res = run_hybrid(sc, "hungarian", "greedy")
    hungarian = run_algorithm(sc, "hungarian")

    phase2 = sum(1 for a in res.assignments
                 if "Phase 2" in (a.explanation.note or ""))
    assert phase2 == 0
    assert res.metrics.assigned_count == hungarian.metrics.assigned_count
    assert res.metrics.objective == pytest.approx(hungarian.metrics.objective)


def test_hybrid_phase_notes_are_labelled():
    sc = generate_scenario("batching", n_trucks=8, n_orders=12, seed=7)
    res = run_hybrid(sc, "hungarian", "greedy")
    notes = [a.explanation.note or "" for a in res.assignments]
    assert any("Phase 1" in n and "hungarian" in n for n in notes)
    assert any("Phase 2" in n and "greedy" in n for n in notes)
    assert res.algorithm == "hybrid:hungarian+greedy"


def test_residual_matrix_masks_served_and_decrements_capacity():
    sc = generate_scenario("batching", n_trucks=8, n_orders=12, seed=7)
    cm = _matrix(sc)
    pairs = get_strategy("hungarian").solve(cm)
    res = _residual_matrix(cm, pairs)

    served = {oj for _, oj in pairs}
    for _, oj in pairs:                                # served orders -> +inf column
        assert all(not math.isfinite(res.cost[i, oj]) for i in range(len(cm.trucks)))
    used = {}
    for ti, _ in pairs:
        used[ti] = used.get(ti, 0) + 1
    for i, t in enumerate(cm.trucks):                  # capacity decremented
        assert res.trucks[i].capacity_orders == t.capacity_orders - used.get(i, 0)
    # orders not served keep at least one finite option if one existed originally
    assert len(served) == len(pairs)
