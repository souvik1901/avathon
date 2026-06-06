"""
Min-Cost Flow strategy — the capacitated generalisation (OR-Tools).

This is the "domain-insight" algorithm. A real truck can carry several small
orders, so one-to-one matching under-uses the fleet. We model the cycle as a flow
network:

    source --(cap = truck.capacity_orders)--> truck
    truck  --(cap = 1, cost = assignment cost)--> order        [feasible pairs only]
    order  --(cap = 1, cost = -SERVE_REWARD)--> sink
    source --(cap = total, cost = 0)--> sink                    [overflow / idle cap]

The huge negative SERVE_REWARD on each order→sink arc makes the solver assign as
many orders as it feasibly can (maximise coverage); the real per-pair costs then
break ties so the chosen assignment is cheapest. With capacity_orders == 1 the
network reduces to bipartite matching and the result equals Hungarian.

OR-Tools works in integers, so costs are scaled and rounded.
"""
from __future__ import annotations

import numpy as np
from ortools.graph.python import min_cost_flow as ortools_mcf

from ..cost import CostMatrix
from .base import AllocationStrategy

_SCALE = 1000  # float cost -> integer units


class MinCostFlowStrategy(AllocationStrategy):
    key = "min_cost_flow"
    name = "Min-Cost Flow (capacitated)"
    optimality = "Optimal (capacitated relaxation)"
    model = "1:many"
    complexity = "Polynomial (network simplex)"
    best_when = "Trucks batch several small orders; fleet under-utilised by 1:1"

    def solve(self, cm: CostMatrix) -> list[tuple[int, int]]:
        n, m = len(cm.trucks), len(cm.orders)
        C = cm.cost
        finite = C[np.isfinite(C)]
        if finite.size == 0:
            return []

        scaled_max = int(np.ceil(np.abs(finite).max() * _SCALE)) + 1
        serve_reward = scaled_max * (n + m) * 10  # dominates any real cost

        smcf = ortools_mcf.SimpleMinCostFlow()
        SOURCE = 0
        SINK = 1
        truck_node = lambda i: 2 + i
        order_node = lambda j: 2 + n + j

        total_capacity = int(sum(t.capacity_orders for t in cm.trucks))

        # source -> truck (capacity = how many orders the truck may take)
        for i, t in enumerate(cm.trucks):
            cap = int(t.capacity_orders)
            if cap > 0:
                smcf.add_arc_with_capacity_and_unit_cost(SOURCE, truck_node(i), cap, 0)

        # truck -> order (only feasible pairs)
        arc_lookup: dict[int, tuple[int, int]] = {}
        for i in range(n):
            for j in range(m):
                if np.isfinite(C[i, j]):
                    cost_int = int(round(C[i, j] * _SCALE))
                    arc = smcf.add_arc_with_capacity_and_unit_cost(
                        truck_node(i), order_node(j), 1, cost_int)
                    arc_lookup[arc] = (i, j)

        # order -> sink (reward for serving)
        for j in range(m):
            smcf.add_arc_with_capacity_and_unit_cost(order_node(j), SINK, 1, -serve_reward)

        # overflow: unused truck capacity drains straight to sink at zero cost
        smcf.add_arc_with_capacity_and_unit_cost(SOURCE, SINK, total_capacity, 0)

        smcf.set_node_supply(SOURCE, total_capacity)
        smcf.set_node_supply(SINK, -total_capacity)

        status = smcf.solve()
        if status != smcf.OPTIMAL:
            return []

        pairs: list[tuple[int, int]] = []
        for arc, (i, j) in arc_lookup.items():
            if smcf.flow(arc) > 0:
                pairs.append((i, j))
        return pairs

    def note_for(self, cm: CostMatrix, ti: int, oj: int) -> str | None:
        cap = cm.trucks[ti].capacity_orders
        if cap > 1:
            return (f"Truck may batch up to {cap} orders this cycle; chosen to "
                    f"minimise total fleet cost across all served orders.")
        return None
