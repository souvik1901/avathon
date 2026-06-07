# Resource Allocation Engine — System Design Document

**Domain:** Delivery Fleet (Trucks → Delivery Orders)
**Stack:** FastAPI (backend) · React + Vite + TypeScript (frontend) · Leaflet/OpenStreetMap (map)
**Status:** Implemented. This document describes both the design and the as-built system; §14 records where the build deviated from the original plan.

---

## 0. How to read this document

This document captures the design of the system: the modelling decisions, the algorithm choices and the trade-offs behind them, and the contracts (data model, API, metrics) the implementation follows. It is deliberately opinionated — it states *why* each decision was made, not just *what* was built. Sections flagged **[SCOPE]** mark where the system deliberately draws a boundary, with the credible extension named.

> **Reading order for "I just want to understand how it works":** §1 (framing) → §4 (architecture) → **§4.1 (runtime flow — the request lifecycle)** → §3 (cost model) → §5 (algorithms). The runtime-flow section ties every module together; the README's *End-to-end flow* section mirrors it with a diagram.

---

## 1. Problem framing

The system assigns **mobile resources (trucks)** to **incoming requests (delivery orders)** so that every order that *can* be served is served, and the assignment is *cheap* under a transparent cost model. The central tension it is built to expose is **local vs. global** optimisation: a greedy dispatcher commits to the locally best truck for each order in turn; a batch optimiser (Hungarian) considers all truck↔order pairings simultaneously and can find a globally cheaper matching. The system implements both, plus a capacitated generalisation (one truck → several orders), and *measures* exactly when and why they diverge.

### 1.1 The core modelling decision — what is "one assignment"?

A real fleet is a **Vehicle Routing Problem (VRP)**: one truck visits many stops along a route. VRP is NP-hard and would dominate the algorithm comparison that is the point of this system. So the system is modelled as a sequence of **dispatch cycles**. At a decision time `T`:

- There is a set of **available trucks** (idle or about to free up).
- There is a set of **open orders** (not yet assigned).
- Each truck is assigned to **at most one** order — its *immediate next job*.

This reframes the per-cycle problem as the classic **Assignment Problem on a bipartite graph** (trucks on one side, orders on the other), which is *exactly* where Greedy and Hungarian are directly and fairly comparable. It is also realistic: many production dispatch systems batch decisions into short time windows.

**[SCOPE]** One-truck-one-order per cycle is the headline model. The system extends to *one-truck-multiple-orders* via a capacitated min-cost-flow strategy (§5.3) to reflect the real fleet shape, and names full multi-stop VRP as out of scope but reachable (§11).

---

## 2. Domain model

Three first-class entities plus the cost model. All coordinates are `(lat, lon)`; all times are timezone-aware UTC instants; durations in minutes. Implemented as Pydantic v2 models in `app/models.py`, so validation, JSON serialisation, and the OpenAPI schema all derive from one source.

### 2.1 Truck (Resource)

| Field | Type | Meaning |
|---|---|---|
| `id` | str | Stable identifier |
| `location` | (lat, lon) | Current/last known position |
| `capacity_weight_kg` | float | Max payload |
| `capacity_volume_m3` | float | Max volume |
| `capabilities` | list[str] | e.g. `["refrigerated", "hazmat", "liftgate"]` |
| `shift_start`, `shift_end` | datetime | Working window |
| `avg_speed_kmph` | float | For travel-time estimation |
| `cost_per_km` | float | Operating cost (fuel, wear) |
| `status` | enum | `idle` / `assigned` / `off_shift` |
| `capacity_orders` | int | Orders the truck may take per cycle (`1` = one-to-one; `>1` = batching) |

### 2.2 Order (Request)

| Field | Type | Meaning |
|---|---|---|
| `id` | str | Stable identifier |
| `pickup`, `dropoff` | (lat, lon) | Stops — the route for an order is `truck → pickup → dropoff` |
| `weight_kg`, `volume_m3` | float | Demand |
| `required_capabilities` | list[str] | Must be a subset of truck capabilities |
| `ready_at` | datetime | Earliest serviceable time |
| `due_by` | datetime | SLA deadline (defines lateness) |
| `priority` | int (1–5) | Higher = more important (weights cost & tie-breaks) |
| `service_time_min` | float | Time on-site at pickup |

### 2.3 Assignment

| Field | Type | Meaning |
|---|---|---|
| `truck_id`, `order_id` | str | The pairing |
| `cost` | float | Resolved soft cost (see §3) |
| `eta` | datetime | Predicted arrival at dropoff |
| `predicted_lateness_min` | float | `max(0, eta − due_by)` |
| `travel_km` | float | Total route distance (deadhead + loaded) |
| `explanation` | object | Cost breakdown + counterfactual + rejections (see §7) |

### 2.4 Scenario

A named bundle of `{trucks[], orders[], weights}` plus a `decision_time`. Scenarios are the unit that is seeded, persisted, run algorithms against, and compared. Reproducibility comes from a `seed`.

---

## 3. Cost model (the heart of the system)

Every algorithm optimises the **same** cost function, so the comparison is apples-to-apples. The only thing that differs between algorithms is *how they search* the assignment space. The cost engine (`app/cost.py`) owns the single source of truth for "how expensive is it to send truck *t* on order *o*".

### 3.1 Hard constraints (feasibility gate)

A truck–order pair is **infeasible** (cost = +∞, never assigned) if any hold:

1. **Capability** — `order.required_capabilities ⊄ truck.capabilities`
2. **Capacity** — `order.weight > truck.capacity_weight` or `order.volume > truck.capacity_volume`
3. **Availability** — truck `status == idle` and the decision time is within `[shift_start, shift_end]`
4. **Time window** — the truck must physically finish before `shift_end`. Concretely: `arrive_pickup = decision_time + travel(truck→pickup)`; `start_service = max(arrive_pickup, ready_at)`; `eta = start_service + service_time + travel(pickup→dropoff)`; require `eta ≤ shift_end`.

Feasibility and cost are computed together, once per cell (`_evaluate_pair`): an infeasible pair is `+∞`, a feasible one carries its full cost decomposition and timeline.

### 3.2 Soft cost (what is minimised)

For a feasible pair `(t, o)`:

```
cost(t, o) =  w_dist  · travel_km · cost_per_km            # deadhead + loaded distance / fuel
            + w_late  · predicted_lateness_min(t, o)        # SLA breach
            + w_idle  · underutilisation(t, o)              # capacity wasted
            - w_prio  · priority(o)                         # favour high-priority (a bonus)
```

- `travel_km` uses the **haversine** great-circle distance × a road-circuity factor (~1.3). Free, deterministic, no external API. **[SCOPE]** A local OSRM instance for true road distance is the named upgrade; haversine is sufficient to make the algorithm comparison meaningful.
- `underutilisation` = fraction of truck capacity left empty (`1 − max(weight_frac, volume_frac)`) — discourages sending a large truck for a tiny parcel when a smaller one is free.
- Weights `w_*` are **scenario parameters exposed as UI sliders**, so the same scenario can be re-optimised under different objectives and the algorithms' behaviour observed live. The default `w_dist = 2.0` keeps the distance term dominant over the priority bonus at metro scale, so the objective stays solidly positive and the optimality gap is stable (a tiny near-zero objective makes the gap percentage blow up).

All weights and the circuity factor live in one `CostConfig` object — single source of truth, injected into every algorithm.

Scenario geography is generated on **real land hubs across the Kolkata metropolitan area** (see `generators.py`) with a small jitter, so every truck/order sits on land and markers spread across distinct towns rather than piling up — dispersed profiles draw from all hubs, clustered profiles from a few adjacent ones.

---

## 4. Architecture

```
┌─────────────────────────── Browser (React + Vite + TS) ───────────────────────────┐
│  Map View (Leaflet/OSM)   Control Panel (scenario, algos, weight sliders)          │
│  Comparison Grid (side-by-side maps + metric cards)   Explanation Drawer            │
└───────────────────────────────────┬───────────────────────────────────────────────┘
                                     │  REST / JSON (fetch)
┌────────────────────────────────────▼──────────────────────────────────────────────┐
│                                FastAPI app                                          │
│  Routers:  /scenarios  /allocate  /allocate/compare  /algorithms                    │
│  Services: ScenarioStore · CostEngine (feasibility + cost) · MetricsEngine · Engine │
│  Strategies (pluggable):  Greedy · Hungarian · MinCostFlow                          │
│  Core libs: NumPy · SciPy (linear_sum_assignment) · OR-Tools (min-cost flow)        │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

- **Stateless compute, in-memory store.** Scenarios live in an in-process dict keyed by id. **[SCOPE]** A `Store` interface lets the persistence layer swap to SQLite/Postgres with zero algorithm changes; the in-memory implementation ships.
- **Strategy pattern** for algorithms: every strategy implements `solve(cost_matrix) -> [(truck_idx, order_idx)]`; the base class turns those raw pairs into explained `AllocationResult`s. New algorithms drop in without touching the API. This is the design lever that makes "compare N algorithms" a one-line loop.
- **No paid services.** Map tiles from OpenStreetMap; everything runs on `localhost`.

### 4.1 Runtime flow — the request lifecycle

The whole system is one pipeline. The UI always (1) generates the scenario, then (2) allocates — and the active tab chooses the allocate call: a single-algorithm tab and Compare All both use `/allocate/compare` (a single-algorithm page runs alongside Hungarian so its gap is filled), while Hybrid Lab uses `/allocate/hybrid`. All three drive the same core loop below. Tracing it end to end is the fastest way to understand the codebase.

**Sequence (the "Run" click):**

```
User ──► ControlPanel ──► App.run()
                            │
   (1) POST /api/scenarios/generate {profile, n_trucks, n_orders, seed}
                            │            ├─ generators.generate_scenario()  → deterministic Scenario
                            │            └─ store.put(scenario)              → in-memory dict
                            │◄── Scenario {id, trucks[], orders[], decision_time, weights}
                            │
   (2) POST /api/allocate/compare {scenario_id, algorithms[], weights?}
                            │            └─ engine.run_comparison():
                            │                 for algo in algorithms:
                            │                   engine.run_algorithm(scenario, algo, weights):
                            │                     a. cost.build_cost_matrix()  → CostMatrix (N×M, +inf=infeasible)
                            │                     b. strategy.allocate(cm):
                            │                          • strategy.solve(cm)         → [(truck_i, order_j), …]
                            │                          • explain.build_assignment() → Assignment + Explanation
                            │                     c. metrics.compute_metrics()  → Metrics
                            │                 fill each result.optimality_gap vs Hungarian baseline
                            │◄── CompareResult {scenario_id, results: {algo → AllocationResult}}
                            │
                            ▼
   MetricsDashboard · ComparisonGrid · MapView · (ExplanationDrawer on route click)
```

**Why this exact ordering matters:**

1. **The cost matrix is built per algorithm run but from the same `(scenario, weights)`** — so every algorithm in a comparison sees an identical matrix. The matrix build (`O(N·M)` feasibility + cost) is the shared substrate; the *only* thing that varies between algorithms is `strategy.solve()`. This is what makes the comparison apples-to-apples and the optimality gap meaningful.
2. **Feasibility and cost are computed together, once, per cell** (`cost._evaluate_pair`). Hard constraints short-circuit to `+∞`; feasible cells carry the full cost decomposition *and* the timeline (ETA, predicted lateness) in a `CellDetail`. That same `CellDetail` later feeds both the metrics and the human-readable explanation — computed once, used three times.
3. **Explanations are produced by the base strategy, not each algorithm.** `solve()` returns only index pairs; `base.allocate()` calls `explain.build_assignment()` for each, so every algorithm yields identically-shaped, equally-transparent output for free. A new algorithm only has to implement *search*.
4. **The optimality gap is a post-pass.** `run_comparison` runs each algorithm independently, then normalises every `objective` against Hungarian's (computing Hungarian on demand if it was not in the requested set). The gap is therefore always defined relative to the provable one-to-one optimum.

**Data shapes as they move through the pipeline:**

```
Scenario(trucks[], orders[], decision_time, weights)
   │  build_cost_matrix
   ▼
CostMatrix(cost: ndarray[N,M], details: CellDetail[N][M])     # +inf where infeasible
   │  strategy.solve
   ▼
[(truck_idx, order_idx), …]                                   # feasible pairs only
   │  explain.build_assignment  (+ metrics.compute_metrics)
   ▼
AllocationResult(assignments: Assignment[], unassigned_order_ids[], metrics: Metrics)
   │  run_comparison  (optimality_gap fill)
   ▼
CompareResult(results: {algorithm → AllocationResult})        # JSON to the browser
```

**Determinism & statelessness.** A scenario is a pure function of `(profile, n_trucks, n_orders, seed)`; allocation is a pure function of `(scenario, algorithm, weights)`. Nothing in the compute path mutates shared state — the only state is the scenario `Store`, written once at generate-time and read at allocate-time. This is why every result is reproducible and why the engine could be horizontally scaled by simply sharing the store.

---

## 5. Allocation algorithms

Three strategies sit behind one interface. All consume the precomputed cost matrix `C` (shape `N_trucks × M_orders`, with `+∞` at infeasible cells) and emit assignments + per-assignment explanations.

### 5.1 Greedy — myopic, sequential

Sort orders by `(priority desc, due_by asc)`. For each order in turn, pick the lowest-cost *still-available* truck (one with spare `capacity_orders`); mark capacity used. This is the "process requests one-by-one, locally optimal" baseline.

- **Complexity:** `O(M · N)` per cycle (re-scanning the column per order).
- **Strength:** trivially fast, naturally **online** (works as orders stream in), easy to explain.
- **Weakness:** a locally cheap early pick can strand a later high-priority order — the optimality gap that the system measures.

### 5.2 Hungarian / Kuhn–Munkres — optimal one-to-one batch

Solve the min-cost bipartite matching on `C` via `scipy.optimize.linear_sum_assignment`. Infeasible cells are set to a large finite sentinel (`BIG_M`, not `inf`, because the solver needs finite weights); any returned pairing that lands on a sentinel is dropped as unassigned. Handles rectangular (unbalanced) matrices natively.

- **Complexity:** `O(n³)` where `n = max(N, M)`. Comfortable to low-thousands per cycle.
- **Strength:** provably **globally optimal** total cost for the one-to-one model — the baseline the others are measured against.
- **Weakness:** strictly one-to-one (no truck-serves-many); cubic scaling; batch-only (needs the full set at decision time).

### 5.3 Min-Cost Flow — capacitated, the real-fleet generalisation

Model allocation as a flow network: `source → truck nodes (cap = capacity_orders each) → feasible edges weighted by cost → order nodes (cap 1) → sink`, plus an `order → sink` arc carrying a large negative `SERVE_REWARD` so serving an order is strongly preferred over dropping it, and a `source → sink` overflow arc that drains unused truck capacity at zero cost. Solved with OR-Tools `SimpleMinCostFlow` (costs are integer-scaled). With `capacity_orders = 1` this reduces to bipartite matching and **equals Hungarian**; with `capacity_orders > 1` it lets one truck pick up multiple compatible nearby orders — what a dispatcher actually does.

- **Complexity:** polynomial (network simplex); OR-Tools handles tens of thousands of edges fast.
- **Strength:** captures the **domain truth** that trucks have capacity for several small orders; optimal for the capacitated relaxation.
- **Weakness:** still ignores intra-route sequencing/time-window interactions between a truck's multiple stops (that is full VRP) — an explicit approximation.

This is the domain-insight strategy: it shows the system understands fleets, not just textbook matching.

### 5.4 Why this set is the right comparison

| Algorithm | Optimality | Model | Complexity | Best when |
|---|---|---|---|---|
| Greedy | Heuristic | 1:1 | O(M·N) | Huge N, low contention, online streaming |
| Hungarian | **Optimal** | 1:1 | O(n³) | Scarcity/contention, batch dispatch |
| Min-Cost Flow | Optimal (capacitated) | 1:many | Poly | Trucks serve multiple small orders |

Three positions on the spectrum: a fast **heuristic** (greedy), the provable **one-to-one optimum** (Hungarian) it is measured against, and the **capacitated generalisation** (min-cost flow) that breaks the one-truck-one-order limit. Each makes a distinct point; none is redundant.

### 5.5 Hybrid — two-phase composition (primary + fill)

The hybrid is not a fifth search algorithm; it is a **composition** of any two of the above, exposed because real dispatch desks routinely stack a clean optimiser with a fast fallback. It answers a concrete question: *does combining two methods serve more orders, more cheaply, than either alone?*

- **Phase 1.** The `primary` strategy solves the full problem on the shared cost matrix.
- **Residual.** The orders it served are removed (their columns → +∞) and every truck's remaining capacity is decremented (`capacity_orders − used`); a truck with no capacity left has its whole row → +∞. The per-cell `details` are shared unchanged, so explanations stay anchored to the original cost model.
- **Phase 2.** The `secondary` strategy solves that residual matrix, placing leftover orders on whatever capacity remains. Because the residual carries the decremented `capacity_orders`, capacity-aware secondaries (greedy, min-cost-flow) behave correctly.
- **Combine.** The two pair-lists are concatenated (orders are disjoint by construction); each assignment is built through the same `explain.build_assignment` and tagged with a *Phase 1 / Phase 2* note.

**Key property — monotone coverage.** Phase 2 can only *add* assignments, so hybrid coverage ≥ primary coverage always. In strict one-to-one profiles (`contested`, `scarce`, `tight_windows`) the primary already consumes every available truck, so the residual has no spare capacity and the hybrid equals the primary exactly. The payoff appears under `batching` (`capacity_orders > 1`): there a one-to-one primary (Hungarian) leaves capacity that the fill phase uses to lift coverage above the one-to-one optimum. This is the same effect Min-Cost Flow captures directly, reached instead by composition — see `ALGORITHMS.md` for the numbers.

`run_hybrid` lives in `engine.py` alongside `run_algorithm`/`run_comparison`; the residual builder is `_residual_matrix`.

---

## 6. Metrics (what is reported and charted)

Computed identically for every algorithm so the comparison is fair (`app/metrics.py`):

- **Coverage** — orders assigned / total (plus the unassigned list with reasons).
- **Total cost** — sum of assigned soft costs.
- **Objective** — `total_cost + w_unassigned · n_unassigned`. The unassigned penalty is **uniform** per order (not priority-weighted) on purpose: at equal coverage the objective reduces to total cost, so the gap is monotonic and a cost-optimal method cannot be "beaten" by one that merely served cheaper orders.
- **Total / avg travel km.**
- **On-time rate**, **avg lateness**, **max lateness** (SLA health).
- **Fleet utilisation** — distinct trucks used / available trucks; **load balance** via coefficient of variation of orders-per-used-truck.
- **Priority-weighted fulfilment** — served priority mass / total priority mass. Reported separately because priority is a genuinely competing goal that the cost objective deliberately does not fold in.
- **Solve wall-clock (ms)** — the cost of optimality.
- **Optimality gap** — each algorithm's `objective` relative to the Hungarian baseline: `(objective − hungarian_objective) / |hungarian_objective|`. A *negative* gap means the algorithm beat one-to-one Hungarian by serving more orders (how Min-Cost Flow wins the batching profile).

---

## 7. Explainability (decision transparency)

For **every** assignment the system returns a structured explanation (`app/explain.py`):

```json
{
  "breakdown": {"distance": 30.0, "lateness": 8.1, "idle": 4.0, "priority": -24.0},
  "runner_up_truck_id": "T-12",
  "runner_up_cost": 47.8,
  "runner_up_delta": 5.7,
  "rejected": [{"truck_id": "T-03", "reason": "missing capability: refrigerated"},
               {"truck_id": "T-09", "reason": "cannot finish before shift end"}],
  "note": "Global optimum assigned a non-cheapest truck here so another order could be served far more cheaply — a trade greedy cannot make."
}
```

- **Greedy** explains locally: the cheapest feasible truck at the moment of decision.
- **Hungarian** surfaces the **opportunity cost** in its `note` — *why* the global optimum sometimes gives an order its *second*-cheapest truck so another order gets a far cheaper one. Clicking an assignment that differs between Greedy and Hungarian shows exactly this global-vs-local trade.

The explanation object is the same shape across algorithms; the UI renders it in a drawer.

---

## 8. API design

FastAPI, Pydantic v2 models, OpenAPI auto-docs at `/docs`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/algorithms` | List strategies + metadata (optimality, model, complexity, best-when) |
| `POST` | `/scenarios` | Create a scenario from an explicit payload |
| `POST` | `/scenarios/generate` | Generate a scenario from `{profile, n_trucks, n_orders, seed}` |
| `GET` | `/scenarios` | List scenario ids |
| `GET` | `/scenarios/{id}` | Fetch a scenario |
| `POST` | `/scenarios/{id}/trucks` · `/orders` | Interactively add a truck / order |
| `POST` | `/allocate` | `{scenario_id, algorithm, weights?}` → assignments + metrics + explanations |
| `POST` | `/allocate/compare` | `{scenario_id, algorithms[], weights?}` → results keyed by algorithm for side-by-side |
| `POST` | `/allocate/hybrid` | `{scenario_id, primary, secondary, weights?}` → one combined two-phase `AllocationResult` |

`/allocate/compare` runs each strategy on the **same** cost matrix and returns a uniform `AllocationResult` per algorithm — the frontend just maps over the dict. Errors use proper HTTP codes (404 unknown scenario, 422 validation via Pydantic / unknown algorithm).

---

## 9. Frontend design

React + Vite + TypeScript. Libraries: **react-leaflet** (map, free OSM/CARTO tiles), **recharts** (metric bars), lightweight state via React hooks. The Vite dev server proxies `/api/*` to the backend on `:8000`, so no CORS setup is needed in development.

The UI is a **tabbed multi-page console** built around one shared scenario. A persistent **left sidebar** (`ControlPanel`) holds the scenario profile (with a live description) + counts + seed and the **six cost-weight sliders** (`w_dist`, `w_late`, `w_idle`, `w_prio`, `w_unassigned`, `circuity_factor`), each with an inline explanation; `App.tsx` owns the scenario and **auto-runs the active tab** whenever an input changes (regenerating the scenario only when its defining inputs change, re-allocating when weights change). Seven tabs:

1. **Four per-algorithm pages** (`AlgorithmPage`) — a dedicated, focused view of *one* algorithm: a hero header (name, tagline, blurb, and the live `optimality / model / complexity / best-when` metadata), six headline **stat cards** (`AlgoStats`, each with a hover ⓘ description), a large interactive **map** of that algorithm's routes, and a rich decision-detail panel: the objective build-up (cost + unassigned penalty), whole-plan **cost-composition** bars, a click-through **assignment list**, and the unassigned-order list. (A single-algorithm page fetches via `/allocate/compare` against Hungarian, so its optimality gap is filled.)
2. **Compare All** (`ComparePage`) — headline callouts, an objective bar chart, the full metric matrix (best = green, worst = red, `MetricsDashboard`), one mini-map per algorithm (`ComparisonGrid`), and a switchable focus map.
3. **Hybrid Lab** (`HybridLab`) — primary/secondary pickers, a plain-language verdict on whether combining helped, a *combined-vs-each-alone* table, stat cards, and a map whose route explanations name the phase that placed each order.
4. **Simulator** (`SimulatorPage`) — pick several scenario *profiles* at once; each is generated (with the shared counts/seed/weights) and solved by all three algorithms. A summary card per profile (best coverage, optimal objective, greedy gap, per-algorithm objective bars) expands on click into a full breakdown — the metric matrix, side-by-side maps, and a narrative of *what's happening and why*.

- **Map / Spatial View** (`MapView`) — **truck icons** (bright when working, dim when idle), **package** markers for pickups (sized by priority, red and pulsing when unassigned), and **pin** markers for dropoffs. Each **assignment route** is drawn in two legs: a dashed faint **deadhead** leg (truck → pickup, empty) and a solid bright **loaded** leg (pickup → dropoff), coloured per algorithm. Hovering any marker or leg pops a styled detail snippet; the view auto-fits to all points.
- **Explanation Drawer** — click any route → cost breakdown + runner-up truck + infeasible-truck reasons + the algorithm's note.

Auto-re-running on a tweaked scenario is deliberate: it is the most convincing way to *see* when each algorithm (or the hybrid) wins.

---

## 10. Testing strategy

Tests prove correctness **and** demonstrate the comparison (166 tests; `backend/tests/`).

**Cost engine (`test_cost.py`):** haversine known distances and zero case; travel-minutes math; each hard constraint rejects exactly when it should (capability, weight, volume, shift/availability); priority and distance weights move the soft cost in the expected direction.

**Strategy correctness (`test_strategies.py`):**
- **Hungarian optimality** — for small `N`, brute-force all permutations and assert Hungarian matches the true minimum.
- **Min-cost flow ≡ Hungarian when `capacity_orders = 1`** — the equivalence that validates the flow model.
- **Greedy can't undercut optimal cost at equal coverage** — `hungarian.total_cost ≤ greedy.total_cost` whenever both serve the same number of orders. (Notably *not* on the penalised objective: Hungarian minimises cost, not coverage, so greedy can occasionally show a lower objective by leaving an order costlier-than-the-penalty unserved — a real property, surfaced rather than hidden.)
- **Validity** — every produced assignment respects capability, capacity, and capacity_orders.
- **Property tests (Hypothesis)** — random feasible scenarios always yield valid assignments.

**Hybrid (`test_hybrid.py`), parametrised over every profile × every primary × every secondary:**
- **Validity** — the combined result is still legal (feasible pairs, each order once, capacity respected).
- **Monotone coverage** — the hybrid never serves fewer orders than the primary alone.
- **Batching payoff** — on `batching`, Phase 2 fills leftover capacity and lifts coverage above one-to-one Hungarian.
- **No-residual identity** — in one-to-one profiles the hybrid equals the primary exactly (Phase 2 adds nothing).
- **Residual builder** — `_residual_matrix` masks served orders and decrements each truck's capacity correctly.

**API/integration (`test_api.py`):** FastAPI `TestClient` over the full request/response cycle — algorithm listing, generate+allocate, compare fills the optimality gap, the hybrid endpoint returns a combined phase-labelled result, 404/422 errors, interactive add.

**Comparison / benchmark harness (`benchmarks/`):** generates scenario **profiles** and tabulates results (the evidence behind `ALGORITHMS.md`):
- `abundant` — trucks ≫ orders, dispersed → Greedy ≈ Hungarian (gap ~0).
- `contested` — orders cluster around few trucks → Greedy gap widens.
- `scarce` — trucks < orders → coverage + priority-fulfilment diverge.
- `tight_windows` — narrow `due_by` → lateness diverges.
- `batching` — trucks carry several orders (`capacity_orders > 1`) → Min-Cost Flow beats one-to-one.

It also runs a **scaling study** timing only the solve step (matrix build excluded) across instance sizes.

---

## 11. Trade-off analysis

*When does each approach win, and when does the difference matter most?*

- **Greedy wins** when resources are **abundant and dispersed** (its myopic pick is usually already optimal), when decisions must be **online/immediate** (orders stream in and you cannot wait to batch), and at **extreme scale** where `O(n³)` is too slow.
- **Hungarian wins** under **contention and scarcity** — when multiple orders compete for the same few good trucks. Greedy gives the first order its cheapest truck; the global optimiser may give it the *second* cheapest so a later, costlier-to-serve order is not stranded. **The gap is largest exactly when demand is concentrated and costs are correlated** (everyone wants the nearest truck) — the situation the `contested`/`scarce` profiles engineer.
- **Min-Cost Flow wins** when the one-to-one assumption is the real limiter — small orders a single truck should batch. It closes the gap between the clean assignment model and the messy fleet reality, and is the only method in the set that can cover *more* orders by consolidating.

The benchmark table quantifies all of this; the UI lets you *feel* it by re-running a contested scenario and watching Hungarian re-route globally while Greedy strands orders. Full numbers and the scaling study are in `ALGORITHMS.md`.

**[SCOPE] What's next:** true road distance via a local OSRM instance; persistence behind the `Store` interface; and full multi-stop VRP (e.g. OR-Tools routing) for intra-route sequencing — the honest step beyond the one-cycle model.

---

## 12. Project structure

```
resource-allocation-engine/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app + routers
│   │   ├── models.py              # Pydantic: Truck, Order, Assignment, Scenario, Metrics
│   │   ├── store.py               # Store interface + InMemoryStore
│   │   ├── cost.py                # haversine, CostConfig, feasibility gate + cost matrix
│   │   ├── engine.py              # run_algorithm / run_comparison / run_hybrid orchestration
│   │   ├── metrics.py             # metrics + optimality gap
│   │   ├── explain.py             # explanation builder
│   │   ├── generators.py          # scenario profiles + seeding
│   │   └── strategies/
│   │       ├── base.py            # AllocationStrategy interface (solve + allocate)
│   │       ├── greedy.py
│   │       ├── hungarian.py
│   │       └── min_cost_flow.py
│   ├── tests/                     # pytest (166): cost, strategies, hybrid, API
│   ├── benchmarks/                # comparison harness + scaling study
│   ├── pyproject.toml
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/            # ControlPanel, AlgorithmPage, ComparePage, HybridLab,
│   │   │                          # SimulatorPage, AlgoStats, MapView, ComparisonGrid,
│   │   │                          # MetricsDashboard, ExplanationDrawer
│   │   ├── api/client.ts          # typed fetch wrapper
│   │   ├── types/index.ts         # model mirrors + per-algo labels/colours
│   │   ├── styles/theme.css       # modern dispatch-console design system
│   │   └── App.tsx                # tab navigation + shared state + orchestration
│   ├── package.json
│   └── vite.config.ts
├── README.md                      # setup + end-to-end flow + API reference
├── SYSTEM_DESIGN.md               # this document
├── ALGORITHMS_OVERVIEW.md         # concise algorithm comparison (showcase)
├── ALGORITHMS.md                  # algorithm implementation deep-dive (annotated code)
└── UI_GUIDE.md                    # UI walkthrough + demo script
```

---

## 13. Risks & decisions log

- **Haversine ≠ road distance.** Accepted; OSRM is the named upgrade. Keeps the system offline and deterministic.
- **`BIG_M` vs `inf` in Hungarian.** SciPy needs finite costs; the system uses a sentinel and drops any matched sentinel pair. Tested explicitly so a "matched" infeasible pair can never leak through.
- **In-memory store.** Fine for single-user/local operation; the `Store` interface guards the upgrade path.
- **One-cycle model hides VRP.** Stated openly; min-cost-flow narrows it; full VRP (OR-Tools routing) is the explicit next step.
- **Uniform vs priority-weighted unassigned penalty.** Chosen uniform so the optimality gap stays monotonic; priority is reported separately rather than folded into the objective.

---

## 14. Implementation notes (where the build refined the plan)

- **Feasibility was merged into the cost engine.** A single pass over the matrix (`_evaluate_pair`) computes feasibility *and* cost *and* the per-cell timeline (`CellDetail`), reused by both metrics and explanations. Splitting feasibility into its own module would have meant walking the matrix twice for no benefit.
- **`engine.py` is the orchestration layer** (`run_algorithm`, `run_comparison`), keeping `main.py` purely HTTP routing. The runtime flow is documented in §4.1.
- **Three core strategies are implemented** (greedy, Hungarian, min-cost flow). An earlier **Auction (Bertsekas)** variant was built and then **removed**: it only reached the same optimum as Hungarian by a different mechanism, and its parallelism advantage doesn't show in serial Python — so it added explanatory weight without changing any of the comparison's conclusions. Trimming it keeps the story focused on the three methods that each make a distinct point.
- **The `batching` profile** (trucks with `capacity_orders > 1`) exists specifically to give Min-Cost Flow a regime where it provably beats the one-to-one optimum; without it MCF would only ever tie Hungarian.
- **Map tiles:** CARTO dark basemaps over OpenStreetMap data (free, no key).
- **Two-phase hybrid (§5.5) was added** as an engine-level composition (`run_hybrid` + `_residual_matrix`) rather than a registry strategy, because it parameterises over two existing strategies. It reuses the same cost matrix, explanation, and metrics machinery, and is fully covered by `test_hybrid.py`.
- **The frontend was restructured into a tabbed multi-page console** (one page per algorithm, a Compare-All page, a Hybrid Lab, and a Simulator) with a shared sidebar and auto-run, replacing the original single all-in-one page. Each single-algorithm page runs against Hungarian so its optimality gap is populated.
- **Scenario geography moved to Kolkata-metro land hubs.** The original free random scatter around a coastal centre dropped points into open water and clustered markers; hub-based placement keeps everything on land and visually spread (see §3, §4.1).
- **Default `w_dist` was raised to 2.0** after the geography change shrank intra-metro distances enough that the priority bonus could drive the objective near zero (destabilising the optimality-gap percentage). Distance now stays dominant and objectives are solidly positive.
- **A test invariant was corrected to the honest property** (see §10): Hungarian is *cost*-optimal (not objective-optimal), so greedy can occasionally win on the penalised objective by leaving an order costlier-than-the-penalty unserved. A genuine finding the build surfaced, now asserted as "at equal coverage, Hungarian's cost ≤ greedy's."
