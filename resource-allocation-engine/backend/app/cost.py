"""
Cost engine.

This module owns the single source of truth for "how expensive is it to send
truck t on order o". Every allocation strategy consumes the same CostMatrix, so
any difference in their output is purely a difference in *search*, never in how
cost is defined. That is what makes the algorithm comparison fair.

The route for one order is:  truck.location -> order.pickup -> order.dropoff
  deadhead leg  = distance(truck -> pickup)   (empty running)
  loaded leg    = distance(pickup -> dropoff) (revenue running)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from .models import CostConfig, GeoPoint, Order, Truck

EARTH_RADIUS_KM = 6371.0088
INFEASIBLE = math.inf


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance in km between two lat/lon points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def road_km(a: GeoPoint, b: GeoPoint, circuity: float) -> float:
    """Approximate road distance = great-circle * a circuity factor (~1.3).
    Cheap, deterministic, offline. (A local OSRM instance is the named upgrade.)"""
    return haversine_km(a, b) * circuity


def travel_minutes(km: float, speed_kmph: float) -> float:
    return (km / speed_kmph) * 60.0 if speed_kmph > 0 else INFEASIBLE


@dataclass
class CellDetail:
    """Everything we computed for one (truck, order) pair — feasibility, the cost
    decomposition, and the timeline. Drives both the matrix and the explanations."""
    feasible: bool
    reason: str = ""                 # why infeasible (empty if feasible)
    total_cost: float = INFEASIBLE
    distance: float = 0.0
    lateness: float = 0.0
    idle: float = 0.0
    priority: float = 0.0
    travel_km: float = 0.0
    eta: datetime | None = None
    predicted_lateness_min: float = 0.0


@dataclass
class CostMatrix:
    """Dense cost matrix + per-cell detail. Rows = trucks, cols = orders."""
    trucks: list[Truck]
    orders: list[Order]
    cost: np.ndarray                 # (n_trucks, n_orders), inf where infeasible
    details: list[list[CellDetail]] = field(default_factory=list)

    def feasible_mask(self) -> np.ndarray:
        return np.isfinite(self.cost)


def _evaluate_pair(truck: Truck, order: Order, dt: datetime, cfg: CostConfig) -> CellDetail:
    """Run the hard-constraint gate, then (if feasible) compute the soft cost."""
    # --- hard constraints -------------------------------------------------
    missing = set(order.required_capabilities) - set(truck.capabilities)
    if missing:
        return CellDetail(False, f"missing capability: {', '.join(sorted(missing))}")
    if order.weight_kg > truck.capacity_weight_kg:
        return CellDetail(False, f"over weight capacity "
                                 f"({order.weight_kg:.0f} > {truck.capacity_weight_kg:.0f} kg)")
    if order.volume_m3 > truck.capacity_volume_m3:
        return CellDetail(False, f"over volume capacity "
                                 f"({order.volume_m3:.1f} > {truck.capacity_volume_m3:.1f} m3)")
    if truck.status != "idle":
        return CellDetail(False, f"truck not idle (status={truck.status})")
    if not (truck.shift_start <= dt <= truck.shift_end):
        return CellDetail(False, "outside truck shift window")

    # --- timeline ---------------------------------------------------------
    deadhead_km = road_km(truck.location, order.pickup, cfg.circuity_factor)
    loaded_km = road_km(order.pickup, order.dropoff, cfg.circuity_factor)
    travel_km = deadhead_km + loaded_km

    arrive_pickup = dt + timedelta(minutes=travel_minutes(deadhead_km, truck.avg_speed_kmph))
    start_service = max(arrive_pickup, order.ready_at)
    depart_pickup = start_service + timedelta(minutes=order.service_time_min)
    eta = depart_pickup + timedelta(minutes=travel_minutes(loaded_km, truck.avg_speed_kmph))

    # Must physically finish within the shift -> hard constraint.
    if eta > truck.shift_end:
        return CellDetail(False, "cannot finish before shift end")

    predicted_lateness_min = max(0.0, (eta - order.due_by).total_seconds() / 60.0)

    # --- soft cost --------------------------------------------------------
    distance = cfg.w_dist * travel_km * truck.cost_per_km
    lateness = cfg.w_late * predicted_lateness_min
    utilisation = max(order.weight_kg / truck.capacity_weight_kg,
                      order.volume_m3 / truck.capacity_volume_m3)
    idle = cfg.w_idle * (1.0 - min(1.0, utilisation))
    priority = -cfg.w_prio * order.priority
    total = distance + lateness + idle + priority

    return CellDetail(
        feasible=True, total_cost=total, distance=distance, lateness=lateness,
        idle=idle, priority=priority, travel_km=travel_km, eta=eta,
        predicted_lateness_min=predicted_lateness_min,
    )


def build_cost_matrix(trucks: list[Truck], orders: list[Order],
                      dt: datetime, cfg: CostConfig) -> CostMatrix:
    n, m = len(trucks), len(orders)
    cost = np.full((n, m), INFEASIBLE, dtype=float)
    details: list[list[CellDetail]] = []
    for i, t in enumerate(trucks):
        row: list[CellDetail] = []
        for j, o in enumerate(orders):
            d = _evaluate_pair(t, o, dt, cfg)
            row.append(d)
            if d.feasible:
                cost[i, j] = d.total_cost
        details.append(row)
    return CostMatrix(trucks=trucks, orders=orders, cost=cost, details=details)
