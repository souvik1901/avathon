"""
Hungarian / Kuhn–Munkres strategy — globally optimal one-to-one matching.

Solves the min-cost bipartite assignment over the full cost matrix at once via
scipy.optimize.linear_sum_assignment (O(n^3)). Infeasible cells are replaced by a
large finite sentinel (the solver cannot take literal infinities); any matched
pair that landed on a sentinel is dropped as genuinely unassigned. Handles
rectangular (unbalanced trucks vs orders) matrices natively.

Each truck takes at most one order here — that is the definition of the
assignment problem. Multi-order-per-truck is the min-cost-flow strategy's job.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

from ..cost import CostMatrix
from .base import AllocationStrategy


class HungarianStrategy(AllocationStrategy):
    key = "hungarian"
    name = "Hungarian (Kuhn–Munkres)"
    optimality = "Optimal (one-to-one)"
    model = "1:1"
    complexity = "O(n³)"
    best_when = "Contention/scarcity; batch dispatch; correlated costs"

    def solve(self, cm: CostMatrix) -> list[tuple[int, int]]:
        C = cm.cost
        finite = C[np.isfinite(C)]
        if finite.size == 0:
            return []
        big_m = (np.abs(finite).max() + 1.0) * (C.shape[0] + C.shape[1]) * 1000.0
        work = np.where(np.isfinite(C), C, big_m)

        rows, cols = linear_sum_assignment(work)
        pairs: list[tuple[int, int]] = []
        for ti, oj in zip(rows, cols):
            if np.isfinite(C[ti, oj]):  # drop sentinel (infeasible) matches
                pairs.append((int(ti), int(oj)))
        return pairs

    def note_for(self, cm: CostMatrix, ti: int, oj: int) -> str | None:
        """Surface the global-vs-local trade-off: did the optimum hand this order
        a *non-cheapest* truck so the fleet total came out lower? That sacrifice
        is precisely what a greedy dispatcher cannot see."""
        col = cm.cost[:, oj]
        feasible_rows = [i for i in range(len(cm.trucks)) if np.isfinite(col[i])]
        if not feasible_rows:
            return None
        local_best = min(feasible_rows, key=lambda i: col[i])
        if local_best != ti:
            delta = float(col[ti] - col[local_best])
            return (f"Global optimum assigned a non-cheapest truck here "
                    f"(+{delta:.1f} locally) so another order could be served far "
                    f"more cheaply — a trade greedy cannot make.")
        return "This truck was also the locally cheapest feasible option."
