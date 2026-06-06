"""Registry of available allocation strategies."""
from __future__ import annotations

from .base import AllocationStrategy
from .greedy import GreedyStrategy
from .hungarian import HungarianStrategy
from .min_cost_flow import MinCostFlowStrategy

STRATEGIES: dict[str, AllocationStrategy] = {
    s.key: s for s in (
        GreedyStrategy(),
        HungarianStrategy(),
        MinCostFlowStrategy(),
    )
}


def get_strategy(key: str) -> AllocationStrategy:
    if key not in STRATEGIES:
        raise KeyError(key)
    return STRATEGIES[key]


__all__ = ["STRATEGIES", "get_strategy", "AllocationStrategy"]
