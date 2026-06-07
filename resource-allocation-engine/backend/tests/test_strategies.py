"""
Strategy tests — the heart of the correctness story.

  * Hungarian == brute-force optimum on small instances.
  * Min-cost-flow == Hungarian when capacity_orders == 1.
  * Greedy never undercuts Hungarian's cost at equal coverage.
  * Every strategy returns a *valid* assignment (capacity & feasibility honoured),
    checked exhaustively and via Hypothesis property tests.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.cost import build_cost_matrix
from app.engine import run_algorithm
from app.generators import generate_scenario
from app.models import CostConfig
from app.strategies import STRATEGIES, get_strategy

PROFILES = ["abundant", "contested", "scarce", "tight_windows", "batching"]


def _matrix(scenario, cfg=None):
    cfg = cfg or CostConfig()
    return build_cost_matrix(scenario.trucks, scenario.orders,
                             scenario.decision_time, cfg)


def _pairs_cost(cm, pairs):
    return sum(cm.cost[i, j] for i, j in pairs)


def _brute_force_optimum(cm):
    """Max-cardinality, then min-cost one-to-one assignment by exhaustion.
    Only used on tiny instances (n,m <= 7)."""
    n, m = cm.cost.shape
    feas = {(i, j) for i in range(n) for j in range(m) if math.isfinite(cm.cost[i, j])}
    best = None
    # try all matchings via permutations of orders onto trucks
    rows = range(n)
    for r in range(min(n, m), -1, -1):  # prefer more assignments first
        found_at_r = False
        for truck_combo in itertools.combinations(rows, r):
            for order_combo in itertools.permutations(range(m), r):
                pairs = list(zip(truck_combo, order_combo))
                if all((i, j) in feas for i, j in pairs):
                    c = sum(cm.cost[i, j] for i, j in pairs)
                    if best is None or c < best[0]:
                        best = (c, r, pairs)
                    found_at_r = True
        if found_at_r:
            # we want max cardinality; once we have any matching of size r, the
            # optimum cardinality is r (we iterate r downward) -> keep min cost at r
            best_at_r = min(
                (sum(cm.cost[i, j] for i, j in zip(tc, oc)), list(zip(tc, oc)))
                for tc in itertools.combinations(rows, r)
                for oc in itertools.permutations(range(m), r)
                if all((i, j) in feas for i, j in zip(tc, oc))
            )
            return r, round(best_at_r[0], 4)
    return 0, 0.0


@pytest.mark.parametrize("seed", [1, 7, 13, 42])
def test_hungarian_matches_brute_force(seed):
    sc = generate_scenario("contested", n_trucks=5, n_orders=6, seed=seed)
    cm = _matrix(sc)
    card, opt_cost = _brute_force_optimum(cm)
    pairs = get_strategy("hungarian").solve(cm)
    assert len(pairs) == card
    assert _pairs_cost(cm, pairs) == pytest.approx(opt_cost, abs=1e-4)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("seed", [7, 11, 42])
def test_flow_equals_hungarian_when_capacity_one(profile, seed):
    sc = generate_scenario(profile, n_trucks=8, n_orders=12, seed=seed)
    for t in sc.trucks:           # force strict one-to-one
        t.capacity_orders = 1
    cm = _matrix(sc)
    h = get_strategy("hungarian").solve(cm)
    f = get_strategy("min_cost_flow").solve(cm)
    assert len(f) == len(h)
    assert _pairs_cost(cm, f) == pytest.approx(_pairs_cost(cm, h), abs=1e-2)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("seed", [7, 11, 42])
def test_greedy_cost_not_below_optimal_at_equal_coverage(profile, seed):
    """Hungarian is cost-optimal for one-to-one matching, so at *equal coverage*
    greedy can never undercut its total cost. (Note: the penalised objective is a
    different quantity — Hungarian minimises cost, not coverage, so greedy can
    occasionally show a lower objective by leaving an order costlier-than-the-
    penalty unserved. That's a real property, not a violation, so we compare cost
    only when both methods serve the same number of orders.)"""
    sc = generate_scenario(profile, n_trucks=8, n_orders=12, seed=seed)
    for t in sc.trucks:
        t.capacity_orders = 1     # strict one-to-one
    g = run_algorithm(sc, "greedy").metrics
    h = run_algorithm(sc, "hungarian").metrics
    if g.assigned_count == h.assigned_count:
        assert h.total_cost <= g.total_cost + 1e-6


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("algo", list(STRATEGIES.keys()))
def test_assignment_is_valid(profile, algo):
    sc = generate_scenario(profile, n_trucks=8, n_orders=12, seed=5)
    cm = _matrix(sc)
    pairs = get_strategy(algo).solve(cm)
    orders_seen, truck_load = set(), {}
    for ti, oj in pairs:
        assert math.isfinite(cm.cost[ti, oj])         # only feasible pairs
        assert oj not in orders_seen                   # each order at most once
        orders_seen.add(oj)
        truck_load[ti] = truck_load.get(ti, 0) + 1
    for ti, load in truck_load.items():                # capacity respected
        assert load <= cm.trucks[ti].capacity_orders


@settings(max_examples=40, deadline=None)
@given(
    n_trucks=st.integers(min_value=1, max_value=8),
    n_orders=st.integers(min_value=1, max_value=8),
    seed=st.integers(min_value=0, max_value=9999),
    algo=st.sampled_from(list(STRATEGIES.keys())),
)
def test_property_valid_assignment(n_trucks, n_orders, seed, algo):
    sc = generate_scenario("contested", n_trucks, n_orders, seed)
    for t in sc.trucks:
        t.capacity_orders = 1
    cm = _matrix(sc)
    pairs = get_strategy(algo).solve(cm)
    orders_seen, trucks_seen = set(), set()
    for ti, oj in pairs:
        assert math.isfinite(cm.cost[ti, oj])
        assert oj not in orders_seen and ti not in trucks_seen
        orders_seen.add(oj)
        trucks_seen.add(ti)
