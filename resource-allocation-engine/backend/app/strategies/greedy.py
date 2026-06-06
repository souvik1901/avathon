"""
Greedy strategy — the myopic baseline.

Process orders one at a time in business priority order (most important / most
urgent first). For each, grab the cheapest still-available truck. A truck is
"used up" once it hits its per-cycle order capacity. This is the textbook
"locally optimal, one-by-one" dispatcher; its weakness is that an early cheap
pick can strand a later order — exactly the optimality gap we measure.
"""
from __future__ import annotations

import numpy as np

from ..cost import CostMatrix
from .base import AllocationStrategy


class GreedyStrategy(AllocationStrategy):
    key = "greedy"
    name = "Greedy (sequential)"
    optimality = "Heuristic"
    model = "1:1 (capacity-aware)"
    complexity = "O(M·N)"
    best_when = "Abundant, dispersed resources; online/streaming arrivals; very large N"

    def solve(self, cm: CostMatrix) -> list[tuple[int, int]]:
        orders = cm.orders
        # Business order: highest priority first, then earliest deadline.
        order_seq = sorted(
            range(len(orders)),
            key=lambda j: (-orders[j].priority, orders[j].due_by),
        )
        remaining = [t.capacity_orders for t in cm.trucks]
        pairs: list[tuple[int, int]] = []
        for oj in order_seq:
            col = cm.cost[:, oj]
            # candidate trucks: feasible AND still have spare capacity, cheapest first
            candidates = sorted(
                (i for i in range(len(cm.trucks))
                 if np.isfinite(col[i]) and remaining[i] > 0),
                key=lambda i: col[i],
            )
            if candidates:
                ti = candidates[0]
                pairs.append((ti, oj))
                remaining[ti] -= 1
        return pairs
