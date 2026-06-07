"""
Turn raw index pairings (truck_i, order_j) produced by a strategy into fully
explained Assignment objects. Centralised here so every algorithm produces
identically-shaped, equally-transparent output.
"""
from __future__ import annotations

import numpy as np

from .cost import CostMatrix
from .models import (Assignment, CostBreakdown, Explanation, RejectedTruck)


def build_assignment(cm: CostMatrix, ti: int, oj: int,
                     note: str | None = None) -> Assignment:
    """Construct one explained Assignment for truck index `ti` <- order index `oj`."""
    truck = cm.trucks[ti]
    order = cm.orders[oj]
    detail = cm.details[ti][oj]

    breakdown = CostBreakdown(
        distance=round(detail.distance, 3),
        lateness=round(detail.lateness, 3),
        idle=round(detail.idle, 3),
        priority=round(detail.priority, 3),
    )

    # Counterfactual: the next-cheapest *feasible* truck for this same order.
    col = cm.cost[:, oj]
    runner_id = runner_cost = runner_delta = None
    order_feasible_rows = [i for i in range(len(cm.trucks)) if np.isfinite(col[i])]
    contenders = sorted(order_feasible_rows, key=lambda i: col[i])
    for i in contenders:
        if i != ti:
            runner_id = cm.trucks[i].id
            runner_cost = round(float(col[i]), 3)
            runner_delta = round(float(col[i] - col[ti]), 3)
            break

    # Hard-rejected trucks for this order, with human reasons.
    rejected = [
        RejectedTruck(truck_id=cm.trucks[i].id, reason=cm.details[i][oj].reason)
        for i in range(len(cm.trucks))
        if not cm.details[i][oj].feasible
    ]

    return Assignment(
        truck_id=truck.id,
        order_id=order.id,
        cost=round(float(cm.cost[ti, oj]), 3),
        eta=detail.eta,
        predicted_lateness_min=round(detail.predicted_lateness_min, 2),
        travel_km=round(detail.travel_km, 3),
        explanation=Explanation(
            breakdown=breakdown,
            runner_up_truck_id=runner_id,
            runner_up_cost=runner_cost,
            runner_up_delta=runner_delta,
            rejected=rejected[:8],  # cap for payload sanity
            note=note,
        ),
    )
