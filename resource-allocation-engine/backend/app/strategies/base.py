"""
Strategy pattern for allocation algorithms.

Every algorithm implements `solve(cost_matrix) -> list[(truck_idx, order_idx)]`.
The base class turns those raw pairs into explained Assignment objects and the
list of unassigned orders, so each concrete strategy stays focused purely on the
*search*. Adding a new algorithm = one subclass; the API and UI pick it up for
free via the registry.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..cost import CostMatrix
from ..explain import build_assignment
from ..models import Assignment


class AllocationStrategy(ABC):
    key: str = "base"
    name: str = "Base"
    optimality: str = ""
    model: str = ""
    complexity: str = ""
    best_when: str = ""

    @abstractmethod
    def solve(self, cm: CostMatrix) -> list[tuple[int, int]]:
        """Return chosen (truck_index, order_index) pairs. Must be feasible
        (finite cost) and respect each truck's capacity_orders."""

    def note_for(self, cm: CostMatrix, ti: int, oj: int) -> str | None:
        """Optional per-assignment commentary (e.g. global vs. local trade-off)."""
        return None

    def allocate(self, cm: CostMatrix) -> tuple[list[Assignment], list[str]]:
        pairs = self.solve(cm)
        assignments = [
            build_assignment(cm, ti, oj, note=self.note_for(cm, ti, oj))
            for ti, oj in pairs
        ]
        assigned_orders = {oj for _, oj in pairs}
        unassigned = [cm.orders[j].id for j in range(len(cm.orders))
                      if j not in assigned_orders]
        return assignments, unassigned
