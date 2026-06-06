"""
Scenario generators.

Profiles are engineered to make the algorithm differences visible and explainable:

  abundant      trucks >> orders, dispersed, loose deadlines  -> greedy ≈ optimal
  contested     orders cluster around a few hubs              -> greedy gap appears
  scarce        fewer trucks than orders                      -> coverage/priority diverge
  tight_windows very narrow due-by windows                    -> lateness diverges
  batching      trucks can carry several small orders (cap>1) -> min-cost-flow wins

All profiles except `batching` keep capacity_orders == 1 so Greedy and Hungarian
are compared strictly one-to-one (apples to apples).

Geography
---------
Points are placed on **real land hubs across the Kolkata metropolitan area** with a
small jitter, never by free random scatter. This keeps every truck/order on land
(the Bay of Bengal is far to the south) and spreads markers across distinct towns so
the map reads cleanly instead of as one cluttered blob. Dispersed profiles draw from
*all* hubs; clustered profiles draw order pickups from a small set of adjacent hubs.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from .models import CostConfig, GeoPoint, Order, Scenario, Truck

# Map framing (Kolkata metro). The Bay of Bengal is well south of ~22.0, so every
# hub below sits comfortably on land.
CENTRE = (22.6300, 88.4000)
DECISION_TIME = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
CAPS = ["refrigerated", "hazmat", "liftgate"]

# Real land hubs spanning the Kolkata metropolitan region (lat, lon). Spread north
# (Naihati/Barrackpore) to south (Sonarpur), west bank (Howrah/Serampore) to east
# (Barasat/New Town) — all on land, avoiding open water.
HUBS: list[tuple[float, float]] = [
    (22.5726, 88.3639),  # 0  Kolkata centre (BBD Bagh)
    (22.5760, 88.4330),  # 1  Salt Lake / Bidhannagar
    (22.6203, 88.4500),  # 2  New Town / Rajarhat
    (22.6420, 88.4310),  # 3  Dum Dum
    (22.6440, 88.3740),  # 4  Baranagar
    (22.7640, 88.3770),  # 5  Barrackpore
    (22.7220, 88.4810),  # 6  Barasat
    (22.6960, 88.4450),  # 7  Madhyamgram
    (22.4980, 88.3700),  # 8  Tollygunge / Garia
    (22.4300, 88.4260),  # 9  Sonarpur
    (22.5090, 88.3140),  # 10 Behala
    (22.7500, 88.3400),  # 11 Serampore (west bank)
    (22.8270, 88.3900),  # 12 Naihati / Halisahar
    (22.5800, 88.2700),  # 13 Howrah / Santragachi
]

# Adjacent eastern hubs used to concentrate demand in the clustered profiles.
HOT_HUBS = [1, 2, 3, 7]


def _near(rng: random.Random, lat: float, lon: float, r: float) -> GeoPoint:
    """A point jittered by up to ±r degrees around a hub (stays local + on land)."""
    return GeoPoint(lat=round(lat + rng.uniform(-r, r), 5),
                    lon=round(lon + rng.uniform(-r, r), 5))


def generate_scenario(profile: str, n_trucks: int, n_orders: int,
                      seed: int, name: str | None = None) -> Scenario:
    rng = random.Random(seed)

    # Profile knobs --------------------------------------------------------
    #   order_hubs : which hubs order pickups draw from (all = dispersed, few = clustered)
    #   jitter     : neighbourhood radius around each hub (deg)
    if profile == "abundant":
        n_trucks = max(n_trucks, int(n_orders * 1.6) + 1)
        order_hubs = list(range(len(HUBS)))          # dispersed everywhere
        jitter = 0.022
        window_min, window_max = 240, 480
        cap_orders = 1
    elif profile == "scarce":
        n_trucks = max(1, min(n_trucks, int(n_orders * 0.6)))
        order_hubs = list(range(len(HUBS)))
        jitter = 0.022
        window_min, window_max = 150, 300
        cap_orders = 1
    elif profile == "tight_windows":
        order_hubs = list(range(len(HUBS)))
        jitter = 0.022
        window_min, window_max = 60, 110             # very tight
        cap_orders = 1
    elif profile == "batching":
        order_hubs = HOT_HUBS                         # small adjacent orders
        jitter = 0.018
        window_min, window_max = 240, 420
        cap_orders = 3                                # trucks may batch
    else:  # "contested" (default)
        profile = "contested"
        order_hubs = HOT_HUBS[:2]                     # demand concentrated on 2 hubs
        jitter = 0.020
        window_min, window_max = 150, 280
        cap_orders = 1

    # Trucks: spread the fleet round-robin across ALL hubs (shuffled per seed) so
    # trucks sit in distinct towns rather than on top of each other.
    truck_hub_order = list(range(len(HUBS)))
    rng.shuffle(truck_hub_order)
    trucks: list[Truck] = []
    for i in range(n_trucks):
        hlat, hlon = HUBS[truck_hub_order[i % len(HUBS)]]
        trucks.append(Truck(
            id=f"T-{i+1:02d}",
            location=_near(rng, hlat, hlon, jitter),
            capacity_weight_kg=rng.choice([800, 1500, 3000, 6000]),
            capacity_volume_m3=rng.choice([4, 8, 16, 30]),
            capabilities=[c for c in CAPS if rng.random() < 0.45],
            shift_start=DECISION_TIME - timedelta(hours=2),
            shift_end=DECISION_TIME + timedelta(hours=10),
            avg_speed_kmph=rng.uniform(35, 55),
            cost_per_km=round(rng.uniform(0.8, 1.5), 2),
            capacity_orders=cap_orders,
        ))

    # Orders: pickups drawn from `order_hubs` (clustered or dispersed); dropoffs
    # scattered across all hubs (deliveries fan out across the metro).
    orders: list[Order] = []
    for j in range(n_orders):
        plat, plon = HUBS[rng.choice(order_hubs)]
        dlat, dlon = HUBS[rng.choice(range(len(HUBS)))]
        orders.append(Order(
            id=f"O-{j+1:02d}",
            pickup=_near(rng, plat, plon, jitter),
            dropoff=_near(rng, dlat, dlon, jitter),
            weight_kg=round(rng.uniform(50, 1200), 1),
            volume_m3=round(rng.uniform(0.5, 12), 1),
            required_capabilities=[c for c in CAPS if rng.random() < 0.18],
            ready_at=DECISION_TIME + timedelta(minutes=rng.uniform(0, 30)),
            due_by=DECISION_TIME + timedelta(minutes=rng.uniform(window_min, window_max)),
            priority=rng.choices([1, 2, 3, 4, 5], weights=[1, 2, 3, 2, 1])[0],
            service_time_min=rng.uniform(5, 20),
        ))

    return Scenario(
        id=f"{profile}-{seed}-{n_trucks}x{n_orders}",
        name=name or f"{profile} ({n_trucks} trucks, {n_orders} orders)",
        trucks=trucks,
        orders=orders,
        decision_time=DECISION_TIME,
        weights=CostConfig(),
        seed=seed,
    )
