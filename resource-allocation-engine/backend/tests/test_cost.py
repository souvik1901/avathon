"""Cost-engine tests: distance, feasibility gates, and the cost decomposition."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import math
import pytest

from app.cost import build_cost_matrix, haversine_km, travel_minutes
from app.models import CostConfig, GeoPoint, Order, Truck

DT = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)


def _truck(**kw) -> Truck:
    base = dict(
        id="T1", location=GeoPoint(lat=19.0, lon=72.8),
        capacity_weight_kg=3000, capacity_volume_m3=20, capabilities=["refrigerated"],
        shift_start=DT - timedelta(hours=1), shift_end=DT + timedelta(hours=8),
        avg_speed_kmph=50, cost_per_km=1.0, capacity_orders=1,
    )
    base.update(kw)
    return Truck(**base)


def _order(**kw) -> Order:
    base = dict(
        id="O1", pickup=GeoPoint(lat=19.05, lon=72.85),
        dropoff=GeoPoint(lat=19.1, lon=72.9), weight_kg=500, volume_m3=4,
        required_capabilities=[], ready_at=DT, due_by=DT + timedelta(hours=4),
        priority=3, service_time_min=10,
    )
    base.update(kw)
    return Order(**base)


def test_haversine_known_distance():
    # ~1 degree of latitude is ~111 km.
    d = haversine_km(GeoPoint(lat=0, lon=0), GeoPoint(lat=1, lon=0))
    assert 110 < d < 112


def test_haversine_zero():
    p = GeoPoint(lat=19.0, lon=72.8)
    assert haversine_km(p, p) == pytest.approx(0.0, abs=1e-9)


def test_travel_minutes():
    assert travel_minutes(50, 50) == pytest.approx(60.0)


def test_feasible_pair_has_finite_cost():
    cm = build_cost_matrix([_truck()], [_order()], DT, CostConfig())
    assert math.isfinite(cm.cost[0, 0])
    assert cm.details[0][0].feasible


def test_missing_capability_is_infeasible():
    cm = build_cost_matrix([_truck(capabilities=[])],
                           [_order(required_capabilities=["hazmat"])], DT, CostConfig())
    assert not math.isfinite(cm.cost[0, 0])
    assert "capability" in cm.details[0][0].reason


def test_over_weight_is_infeasible():
    cm = build_cost_matrix([_truck(capacity_weight_kg=100)],
                           [_order(weight_kg=500)], DT, CostConfig())
    assert not math.isfinite(cm.cost[0, 0])
    assert "weight" in cm.details[0][0].reason


def test_over_volume_is_infeasible():
    cm = build_cost_matrix([_truck(capacity_volume_m3=1)],
                           [_order(volume_m3=10)], DT, CostConfig())
    assert not math.isfinite(cm.cost[0, 0])
    assert "volume" in cm.details[0][0].reason


def test_off_shift_is_infeasible():
    cm = build_cost_matrix([_truck(shift_start=DT + timedelta(hours=2),
                                   shift_end=DT + timedelta(hours=6))],
                           [_order()], DT, CostConfig())
    assert not math.isfinite(cm.cost[0, 0])


def test_priority_weight_lowers_cost():
    lo = build_cost_matrix([_truck()], [_order(priority=1)], DT, CostConfig())
    hi = build_cost_matrix([_truck()], [_order(priority=5)], DT, CostConfig())
    assert hi.cost[0, 0] < lo.cost[0, 0]  # higher priority => cheaper (bonus)


def test_distance_weight_scales_cost():
    near = _order(pickup=GeoPoint(lat=19.0, lon=72.8))
    far = _order(pickup=GeoPoint(lat=19.0, lon=73.5))
    cm = build_cost_matrix([_truck()], [near, far], DT, CostConfig())
    # farther pickup => more travel => higher distance term => higher cost
    assert cm.details[0][1].distance > cm.details[0][0].distance
