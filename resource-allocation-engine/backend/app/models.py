"""
Domain data model for the Resource Allocation Engine (delivery-fleet domain).

Everything the API accepts or returns is defined here as a Pydantic v2 model, so
validation, serialisation and the OpenAPI schema all come for free. The algorithms
themselves operate on these objects (never on raw dicts), which keeps the strategy
layer honest about what a Truck or an Order actually is.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Geography
# ---------------------------------------------------------------------------
class GeoPoint(BaseModel):
    """A latitude/longitude pair. Used for every spatial coordinate in the system."""
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


# ---------------------------------------------------------------------------
# Resources (Trucks)
# ---------------------------------------------------------------------------
class TruckStatus(str, Enum):
    idle = "idle"
    assigned = "assigned"
    off_shift = "off_shift"


class Truck(BaseModel):
    """A mobile resource. Has a location, a capacity envelope, a set of
    capabilities, a working shift and operating economics."""
    model_config = ConfigDict(use_enum_values=True)

    id: str
    location: GeoPoint
    capacity_weight_kg: float = Field(..., gt=0)
    capacity_volume_m3: float = Field(..., gt=0)
    capabilities: list[str] = Field(default_factory=list)
    shift_start: datetime
    shift_end: datetime
    avg_speed_kmph: float = Field(default=50.0, gt=0)
    cost_per_km: float = Field(default=1.0, ge=0)
    status: TruckStatus = TruckStatus.idle
    # How many orders this truck may take in a single dispatch cycle.
    # capacity_orders == 1  -> classic one-to-one assignment (Greedy / Hungarian).
    # capacity_orders  > 1  -> capacitated assignment (min-cost flow).
    capacity_orders: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Requests (Orders)
# ---------------------------------------------------------------------------
class Order(BaseModel):
    """A delivery request. Multi-stop: it has a pickup and a dropoff, demand,
    required capabilities, a service-time window and a priority."""
    id: str
    pickup: GeoPoint
    dropoff: GeoPoint
    weight_kg: float = Field(..., gt=0)
    volume_m3: float = Field(..., gt=0)
    required_capabilities: list[str] = Field(default_factory=list)
    ready_at: datetime
    due_by: datetime
    priority: int = Field(default=3, ge=1, le=5)
    service_time_min: float = Field(default=10.0, ge=0)


# ---------------------------------------------------------------------------
# Cost configuration (shared by every algorithm)
# ---------------------------------------------------------------------------
class CostConfig(BaseModel):
    """Weights for the soft-cost terms plus physical constants. Exposed to the UI
    as sliders so the same scenario can be re-optimised under different objectives.
    A single CostConfig is injected into every strategy, guaranteeing the algorithm
    comparison is apples-to-apples."""
    w_dist: float = Field(default=2.0, ge=0)      # per km of total travel (× truck cost_per_km)
    w_late: float = Field(default=2.0, ge=0)      # per minute of predicted lateness
    w_idle: float = Field(default=5.0, ge=0)      # per unit of wasted capacity (0..1)
    w_prio: float = Field(default=8.0, ge=0)      # bonus per priority point (subtracted)
    w_unassigned: float = Field(default=100.0, ge=0)  # flat penalty per unserved order
    circuity_factor: float = Field(default=1.3, ge=1.0)  # haversine -> approx road km


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------
class Scenario(BaseModel):
    """A named, reproducible bundle of trucks + orders + a decision time + cost
    weights. The unit we seed, store, allocate against and compare."""
    id: str
    name: str = "scenario"
    trucks: list[Truck]
    orders: list[Order]
    decision_time: datetime
    weights: CostConfig = Field(default_factory=CostConfig)
    seed: Optional[int] = None


class ScenarioGenerateRequest(BaseModel):
    """Ask the server to synthesise a scenario from a named profile + seed."""
    profile: str = Field(default="contested")  # abundant|contested|scarce|tight_windows
    n_trucks: int = Field(default=8, ge=1, le=200)
    n_orders: int = Field(default=10, ge=1, le=400)
    seed: int = 42
    name: Optional[str] = None


# ---------------------------------------------------------------------------
# Assignment + result
# ---------------------------------------------------------------------------
class CostBreakdown(BaseModel):
    distance: float = 0.0
    lateness: float = 0.0
    idle: float = 0.0
    priority: float = 0.0  # already negative (a bonus)

    @property
    def total(self) -> float:
        return self.distance + self.lateness + self.idle + self.priority


class RejectedTruck(BaseModel):
    truck_id: str
    reason: str


class Explanation(BaseModel):
    """Decision transparency for one assignment: why this truck, what it nearly
    was (runner-up), and which trucks were hard-rejected and why."""
    breakdown: CostBreakdown
    runner_up_truck_id: Optional[str] = None
    runner_up_cost: Optional[float] = None
    runner_up_delta: Optional[float] = None
    rejected: list[RejectedTruck] = Field(default_factory=list)
    note: Optional[str] = None  # algorithm-specific commentary (e.g. global trade-off)


class Assignment(BaseModel):
    truck_id: str
    order_id: str
    cost: float
    eta: datetime
    predicted_lateness_min: float
    travel_km: float
    explanation: Explanation


class Metrics(BaseModel):
    algorithm: str
    assigned_count: int
    total_orders: int
    coverage: float                 # assigned / total
    total_cost: float
    objective: float                # total_cost + penalty for unassigned orders (gap basis)
    total_travel_km: float
    avg_travel_km: float
    on_time_rate: float
    avg_lateness_min: float
    max_lateness_min: float
    fleet_utilisation: float        # used trucks / available trucks
    load_balance_cv: float          # coefficient of variation of per-truck load
    priority_weighted_fulfilment: float
    solve_ms: float
    optimality_gap: Optional[float] = None  # vs Hungarian, filled by compare endpoint


class AllocationResult(BaseModel):
    algorithm: str
    assignments: list[Assignment]
    unassigned_order_ids: list[str]
    metrics: Metrics


class CompareResult(BaseModel):
    scenario_id: str
    results: dict[str, AllocationResult]


class AlgorithmInfo(BaseModel):
    key: str
    name: str
    optimality: str
    model: str
    complexity: str
    best_when: str
