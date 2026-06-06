"""
Scenario persistence.

A tiny interface (Store) with an in-memory implementation. The interface is the
point: swapping to SQLite/Postgres later touches only this file, never the
algorithms or the API handlers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Scenario


class Store(ABC):
    @abstractmethod
    def put(self, scenario: Scenario) -> None: ...
    @abstractmethod
    def get(self, scenario_id: str) -> Scenario | None: ...
    @abstractmethod
    def list_ids(self) -> list[str]: ...


class InMemoryStore(Store):
    def __init__(self) -> None:
        self._data: dict[str, Scenario] = {}

    def put(self, scenario: Scenario) -> None:
        self._data[scenario.id] = scenario

    def get(self, scenario_id: str) -> Scenario | None:
        return self._data.get(scenario_id)

    def list_ids(self) -> list[str]:
        return list(self._data.keys())
