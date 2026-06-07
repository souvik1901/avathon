"""
Engine service. Glues cost matrix -> strategy -> metrics into an AllocationResult,
and provides the multi-algorithm comparison (filling the optimality gap vs
Hungarian) plus the two-phase hybrid (primary algorithm + secondary fill).
"""
from __future__ import annotations

import time

from .cost import INFEASIBLE, CostMatrix, build_cost_matrix
from .explain import build_assignment
from .logging_utils import get_logger
from .metrics import compute_metrics
from .models import (AllocationResult, CompareResult, CostConfig, Scenario)
from .strategies import get_strategy

log = get_logger()


def _weights_summary(cfg: CostConfig, scenario: Scenario) -> str:
    origin = "custom" if cfg is not scenario.weights else "default"
    return (f"w_dist={cfg.w_dist:g} w_late={cfg.w_late:g} w_idle={cfg.w_idle:g} "
            f"w_prio={cfg.w_prio:g} [{origin}]")


def _log_matrix(cm: CostMatrix, tag: str) -> None:
    n, m = cm.cost.shape
    feasible = int(cm.feasible_mask().sum())
    total = n * m
    pct = (feasible / total * 100.0) if total else 0.0
    log.info("  %s cost matrix: %d trucks x %d orders = %d cells | "
             "feasible=%d (%.0f%%) infeasible=%d",
             tag, n, m, total, feasible, pct, total - feasible)


def _log_result(algorithm: str, r: AllocationResult) -> None:
    mx = r.metrics
    log.info("  ✓ %-14s %2d/%-2d served (%.0f%%) | cost=%.1f obj=%.1f | "
             "on-time=%.0f%% avg-late=%.0fmin | fleet=%.0f%% prio=%.0f%% | %.2fms",
             algorithm, mx.assigned_count, mx.total_orders, mx.coverage * 100,
             mx.total_cost, mx.objective, mx.on_time_rate * 100,
             mx.avg_lateness_min, mx.fleet_utilisation * 100,
             mx.priority_weighted_fulfilment * 100, mx.solve_ms)


def run_algorithm(scenario: Scenario, algorithm: str,
                  weights: CostConfig | None = None,
                  _quiet: bool = False) -> AllocationResult:
    cfg = weights or scenario.weights
    cm = build_cost_matrix(scenario.trucks, scenario.orders,
                           scenario.decision_time, cfg)
    strategy = get_strategy(algorithm)

    if not _quiet:
        log.info("SOLVE  algorithm=%s  scenario=%s (name=%r seed=%s)",
                 algorithm, scenario.id, scenario.name, scenario.seed)
        log.info("  weights: %s", _weights_summary(cfg, scenario))
        _log_matrix(cm, "->")

    t0 = time.perf_counter()
    assignments, unassigned = strategy.allocate(cm)
    solve_ms = (time.perf_counter() - t0) * 1000.0

    metrics = compute_metrics(algorithm, assignments,
                              scenario.trucks, scenario.orders, solve_ms, cfg)
    result = AllocationResult(
        algorithm=algorithm,
        assignments=assignments,
        unassigned_order_ids=unassigned,
        metrics=metrics,
    )
    if not _quiet:
        _log_result(algorithm, result)
    return result


def run_comparison(scenario: Scenario, algorithms: list[str],
                   weights: CostConfig | None = None) -> CompareResult:
    cfg = weights or scenario.weights
    t_all = time.perf_counter()
    log.info("=" * 68)
    log.info("COMPARE scenario=%s (name=%r seed=%s) | %d trucks x %d orders | "
             "algorithms=[%s]", scenario.id, scenario.name, scenario.seed,
             len(scenario.trucks), len(scenario.orders), ", ".join(algorithms))
    log.info("  weights: %s", _weights_summary(cfg, scenario))
    cm = build_cost_matrix(scenario.trucks, scenario.orders,
                           scenario.decision_time, cfg)
    _log_matrix(cm, "->")

    results = {algo: run_algorithm(scenario, algo, weights, _quiet=True)
               for algo in algorithms}
    for algo, res in results.items():
        _log_result(algo, res)

    # Headline metric: how much worse is each algorithm's objective vs
    # Hungarian's optimal one-to-one objective on the same scenario? The
    # objective folds in unassigned-order penalties, so stranding orders is
    # correctly counted against an algorithm (not rewarded as "cheaper").
    baseline = results.get("hungarian")
    if baseline is None:
        baseline = run_algorithm(scenario, "hungarian", weights, _quiet=True)
    base_obj = baseline.metrics.objective
    for res in results.values():
        if abs(base_obj) > 1e-9:
            res.metrics.optimality_gap = round(
                (res.metrics.objective - base_obj) / abs(base_obj), 4)
        else:
            res.metrics.optimality_gap = 0.0

    log.info("  baseline=hungarian obj=%.1f | optimality gaps (obj vs baseline):",
             base_obj)
    for algo, res in results.items():
        gap = res.metrics.optimality_gap or 0.0
        verdict = ("= optimal" if abs(gap) < 1e-9 else
                   f"{'beats' if gap < 0 else 'behind'} baseline")
        log.info("     %-14s %+.1f%%  (%s)", algo, gap * 100, verdict)
    log.info("DONE compare in %.2fms", (time.perf_counter() - t_all) * 1000.0)
    return CompareResult(scenario_id=scenario.id, results=results)


def _residual_matrix(cm: CostMatrix, pairs: list[tuple[int, int]]) -> CostMatrix:
    """Build the residual problem left after `pairs` are committed: orders already
    served are removed (their columns -> +inf) and every truck's remaining
    capacity is decremented (a truck with no capacity left has its row -> +inf).
    The per-cell `details` are shared unchanged, so explanations stay anchored to
    the original cost model. This lets ANY secondary strategy solve the leftover
    using the exact same machinery — including capacity-aware ones (greedy,
    min-cost-flow read `capacity_orders` off the cloned trucks)."""
    cost = cm.cost.copy()

    served = {oj for _, oj in pairs}
    for oj in served:
        cost[:, oj] = INFEASIBLE

    used = {}
    for ti, _ in pairs:
        used[ti] = used.get(ti, 0) + 1

    new_trucks = []
    for i, t in enumerate(cm.trucks):
        remaining = t.capacity_orders - used.get(i, 0)
        if remaining <= 0:
            cost[i, :] = INFEASIBLE
        # model_copy bypasses validation, so remaining==0 is fine; both the
        # greedy (`remaining>0`) and min-cost-flow (`cap>0`) guards skip it.
        new_trucks.append(t.model_copy(update={"capacity_orders": remaining}))

    return CostMatrix(trucks=new_trucks, orders=cm.orders, cost=cost,
                      details=cm.details)


def run_hybrid(scenario: Scenario, primary: str, secondary: str,
               weights: CostConfig | None = None) -> AllocationResult:
    """Two-phase allocation. Phase 1: the `primary` strategy solves the full
    problem. Phase 2: the `secondary` strategy fills any orders the primary left
    unassigned, using only the trucks that still have spare capacity. The result
    is a single combined AllocationResult; each assignment's note records which
    phase produced it."""
    cfg = weights or scenario.weights
    cm = build_cost_matrix(scenario.trucks, scenario.orders,
                           scenario.decision_time, cfg)
    prim, sec = get_strategy(primary), get_strategy(secondary)

    log.info("=" * 68)
    log.info("HYBRID scenario=%s | phase1=%s (solve all) -> phase2=%s (fill gaps)",
             scenario.id, primary, secondary)
    log.info("  weights: %s", _weights_summary(cfg, scenario))
    _log_matrix(cm, "->")

    t0 = time.perf_counter()
    pairs_a = prim.solve(cm)
    residual = _residual_matrix(cm, pairs_a)
    n_free = int((residual.feasible_mask().any(axis=0)).sum())
    log.info("  phase 1 (%s): assigned %d orders | %d orders still open, "
             "feasible for phase 2", primary, len(pairs_a), n_free)
    pairs_b = sec.solve(residual)
    log.info("  phase 2 (%s): filled %d more order(s)", secondary, len(pairs_b))
    solve_ms = (time.perf_counter() - t0) * 1000.0

    # The residual already masks served orders, but guard against any overlap.
    served_a = {oj for _, oj in pairs_a}
    pairs_b = [(ti, oj) for ti, oj in pairs_b if oj not in served_a]

    note_a = f"Phase 1 — assigned by the primary strategy ({primary})."
    note_b = (f"Phase 2 — filled by the secondary strategy ({secondary}) "
              f"after {primary} left it unassigned.")
    assignments = (
        [build_assignment(cm, ti, oj, note=note_a) for ti, oj in pairs_a]
        + [build_assignment(cm, ti, oj, note=note_b) for ti, oj in pairs_b]
    )
    assigned = {oj for _, oj in (pairs_a + pairs_b)}
    unassigned = [cm.orders[j].id for j in range(len(cm.orders)) if j not in assigned]

    label = f"hybrid:{primary}+{secondary}"
    metrics = compute_metrics(label, assignments, scenario.trucks,
                              scenario.orders, solve_ms, cfg)
    result = AllocationResult(algorithm=label, assignments=assignments,
                              unassigned_order_ids=unassigned, metrics=metrics)
    _log_result(label, result)
    log.info("DONE hybrid in %.2fms", solve_ms)
    return result
