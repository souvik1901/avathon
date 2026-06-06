"""
Metrics engine. Computes the same set of metrics for every algorithm so the
comparison grid is fair, plus the headline optimality gap (vs Hungarian).
"""
from __future__ import annotations

import numpy as np

from .models import Assignment, CostConfig, Metrics, Order, Truck


def compute_metrics(algorithm: str, assignments: list[Assignment],
                    trucks: list[Truck], orders: list[Order],
                    solve_ms: float, cfg: CostConfig) -> Metrics:
    total_orders = len(orders)
    assigned_count = len(assignments)
    coverage = assigned_count / total_orders if total_orders else 0.0

    total_cost = float(sum(a.cost for a in assignments))
    total_km = float(sum(a.travel_km for a in assignments))
    avg_km = total_km / assigned_count if assigned_count else 0.0

    # Objective = assignment cost + a flat penalty for every order left unserved.
    # Keeping the penalty uniform (not priority-weighted) makes it a clean
    # coverage-vs-cost objective: at equal coverage it reduces to total cost, so
    # the optimality gap is monotonic and the cost-optimal methods are never
    # "beaten" by an algorithm that simply served cheaper orders. Priority is a
    # genuinely competing goal, so it is reported on its own (see
    # priority_weighted_fulfilment) rather than folded into this baseline.
    assigned_ids = {a.order_id for a in assignments}
    n_unassigned = sum(1 for o in orders if o.id not in assigned_ids)
    unassigned_penalty = cfg.w_unassigned * n_unassigned
    objective = total_cost + unassigned_penalty

    lateness = [a.predicted_lateness_min for a in assignments]
    on_time = sum(1 for l in lateness if l <= 1e-6)
    on_time_rate = on_time / assigned_count if assigned_count else 0.0
    avg_late = float(np.mean(lateness)) if lateness else 0.0
    max_late = float(np.max(lateness)) if lateness else 0.0

    # Fleet utilisation: distinct trucks used / trucks that were available (idle, on shift)
    available = [t for t in trucks if t.status == "idle"]
    used_trucks = {a.truck_id for a in assignments}
    fleet_util = len(used_trucks) / len(available) if available else 0.0

    # Load balance: coefficient of variation of #orders per *used* truck.
    if used_trucks:
        per_truck: dict[str, int] = {}
        for a in assignments:
            per_truck[a.truck_id] = per_truck.get(a.truck_id, 0) + 1
        loads = np.array(list(per_truck.values()), dtype=float)
        cv = float(loads.std() / loads.mean()) if loads.mean() > 0 else 0.0
    else:
        cv = 0.0

    # Priority-weighted fulfilment: served priority mass / total priority mass.
    order_prio = {o.id: o.priority for o in orders}
    total_prio = sum(order_prio.values())
    served_prio = sum(order_prio[a.order_id] for a in assignments)
    pwf = served_prio / total_prio if total_prio else 0.0

    return Metrics(
        algorithm=algorithm,
        assigned_count=assigned_count,
        total_orders=total_orders,
        coverage=round(coverage, 4),
        total_cost=round(total_cost, 3),
        objective=round(objective, 3),
        total_travel_km=round(total_km, 3),
        avg_travel_km=round(avg_km, 3),
        on_time_rate=round(on_time_rate, 4),
        avg_lateness_min=round(avg_late, 2),
        max_lateness_min=round(max_late, 2),
        fleet_utilisation=round(fleet_util, 4),
        load_balance_cv=round(cv, 4),
        priority_weighted_fulfilment=round(pwf, 4),
        solve_ms=round(solve_ms, 3),
    )
