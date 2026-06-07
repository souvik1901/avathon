# Resource Allocation Engine — Delivery Fleet

Assigns a fleet of delivery **trucks** to pickup-and-dropoff **orders**, then lets you
compare three allocation algorithms side-by-side on the same scenario — spatially (on a
map), numerically (metrics), and per-decision (why each truck got each order).

Backend is **FastAPI + Python**; frontend is **React + Vite + TypeScript** with
**Leaflet / OpenStreetMap**. Everything runs locally with no API keys.

> The algorithm comparison comes in two depths: a concise showcase in
> **[`ALGORITHMS_OVERVIEW.md`](./ALGORITHMS_OVERVIEW.md)** (what each method does, when it wins),
> and a full implementation deep-dive with line-by-line code walkthroughs in
> **[`ALGORITHMS.md`](./ALGORITHMS.md)**. The design rationale lives in
> **[`SYSTEM_DESIGN.md`](./SYSTEM_DESIGN.md)**; a UI walkthrough/demo script in
> **[`UI_GUIDE.md`](./UI_GUIDE.md)**.

---

## The problem

> Optimally assign **mobile resources** to **incoming requests**: resources sit at various
> locations with different capabilities and schedules; requests each carry a location, timing,
> and requirements; the engine pairs them up as cheaply as possible.

The domain modelled here is a **delivery fleet** — trucks (resources) assigned to delivery
orders (requests) — chosen for its rich, intuitive constraint set (capacity, capabilities,
shifts, time windows, priority). The pieces and where each lives:

| Capability | Where it lives |
| --- | --- |
| **Data model** — resources, requests, assignments | [`backend/app/models.py`](./backend/app/models.py) — `Truck`, `Order`, `Assignment`, `Scenario` (Pydantic v2) |
| **Allocation strategies** | **Three**: Greedy, Hungarian, Min-Cost Flow — [`backend/app/strategies/`](./backend/app/strategies/) (plus a two-phase Hybrid) |
| **Hard + soft constraints** | [`backend/app/cost.py`](./backend/app/cost.py) — feasibility gate (hard) + weighted soft cost |
| **Decision explanation** | [`backend/app/explain.py`](./backend/app/explain.py) — cost breakdown, runner-up, rejection reasons |
| **Meaningful metrics** | [`backend/app/metrics.py`](./backend/app/metrics.py) — coverage, objective, gap, on-time, utilisation… |
| **Tests + algorithm comparison** | [`backend/tests/`](./backend/tests/) (166 tests) + [`backend/benchmarks/`](./backend/benchmarks/) |
| **Web UI**: map view, side-by-side comparison, metrics | [`frontend/`](./frontend/) — React + Leaflet, tabbed multi-page console |
| **Brief write-up comparing algorithms** | [`ALGORITHMS_OVERVIEW.md`](./ALGORITHMS_OVERVIEW.md) (showcase) · [`ALGORITHMS.md`](./ALGORITHMS.md) (deep-dive) |
| **React frontend, FastAPI backend, free/local only** | Yes — no API keys, no paid services |

---

## What it does

- Models a delivery fleet: trucks with capacity, capabilities, shifts, and locations;
  orders with pickup/dropoff, weight/volume, time windows, and priority.
- Scores every (truck, order) pair through one **shared cost model** — hard constraints
  gate feasibility, soft costs (distance, lateness, idle, priority) rank the rest — so all
  algorithms optimise the *same* objective and the comparison is fair.
- Runs three allocators over that cost matrix: **Greedy**, **Hungarian**, and
  **Min-Cost Flow** (OR-Tools).
- Also offers a **two-phase hybrid**: a *primary* algorithm solves the full problem, then a
  *secondary* algorithm fills any orders left unassigned using trucks with spare capacity —
  to test whether combining two methods serves more orders, more cheaply, than either alone.
- Reports meaningful metrics (coverage, objective, optimality gap, on-time rate, fleet
  utilisation, load balance, priority fulfilment, solve time) and a human-readable
  **explanation** for every assignment (cost breakdown, the runner-up truck and its
  opportunity cost, and which trucks were rejected and why).
- Ships a **tabbed dispatch-console web UI**: a dedicated, interactive page per algorithm,
  a *Compare All* page (side-by-side maps + metric matrix), and a *Hybrid Lab*. Generate a
  scenario, drag the cost-weight sliders (everything re-runs live), see routes on a map, and
  click any route to open its decision explanation.

---

## Quick start

You need **two terminals** — backend on `:8000`, frontend on `:5173`.

### 1. Backend (FastAPI)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # optional but recommended
pip install -r requirements.txt
uvicorn app.main:app --reload                          # serves http://localhost:8000
```

Interactive API docs (Swagger) at <http://localhost:8000/docs>.

### 2. Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev                                            # serves http://localhost:5173
```

Open <http://localhost:5173>. The Vite dev server proxies `/api/*` to the backend on
`:8000`, so no CORS setup is needed. The app auto-runs a default scenario on load.

### Run the tests

```bash
cd backend
pytest                                                 # 166 tests
```

### Run the benchmarks

```bash
cd backend
python -m benchmarks.run_benchmarks                    # profile table + scaling study
python -m benchmarks.run_benchmarks --json bench.json  # also dump raw results
```

---

## Using the console

The UI is organised as **seven tabs** across the top. The left sidebar (scenario profile,
truck/order counts, seed, and six cost-weight sliders each with an inline description) is shared
by every tab and **re-runs the active tab automatically** whenever you change anything — there's
no need to keep pressing Run. Scenario points are placed on real **Kolkata-metro land hubs**, so
they spread across distinct towns and stay off the water. A full walkthrough / demo script lives
in **[`UI_GUIDE.md`](./UI_GUIDE.md)**.

| Tab | What it shows |
| --- | --- |
| **Greedy / Hungarian / Min-Cost Flow** | A dedicated page for *one* algorithm: a hero header explaining it (optimality, model, complexity, best-when), six headline stat cards (each with a hover ⓘ description), a large interactive map of its routes, and a rich decision-detail panel — objective build-up, whole-plan cost composition bars, a click-through assignment list, and the unassigned orders. |
| **Compare All** | All selected algorithms at once: headline callouts, an objective bar chart, the full metric matrix (best = green, worst = red), one mini-map per algorithm, and a focus map you can switch between algorithms. |
| **Hybrid Lab** | Pick a *primary* and a *secondary* strategy; see the two-phase combined result, a verdict on whether combining helped, a *combined-vs-each-alone* table, stat cards, and a map whose route explanations say which phase placed each order. |
| **Simulator** | Select several scenario profiles at once; each is generated and solved by all three algorithms, summarised on a card (best coverage, optimal objective, greedy gap, per-algorithm objective bars). Click a card to open a full breakdown — metric matrix, side-by-side maps, and a note on *what's happening and why*. |

**A good first tour:** open **Hungarian** (the optimal baseline), then **Greedy** and watch the
objective rise — switch to *Tight windows* to make the gap vivid. Use **Compare All** to see them
side by side. Open **Hybrid Lab**, choose the *Batching* profile with `Hungarian → Greedy`, and
watch the fill phase lift coverage past Hungarian alone. Finally open the **Simulator** and select
*contested + batching + abundant* to see all three regimes side by side.

---

## Architecture

```
backend/
  app/
    models.py          Pydantic domain models (Truck, Order, Assignment, Metrics, …)
    cost.py            shared cost model: hard-constraint gate + soft cost matrix
    explain.py         per-assignment explanation (breakdown, runner-up, rejections)
    metrics.py         coverage, objective, utilisation, load balance, optimality gap
    strategies/
      base.py          AllocationStrategy ABC (solve -> [(truck, order)] + allocate())
      greedy.py        priority-ordered greedy
      hungarian.py     SciPy linear_sum_assignment (optimal one-to-one)
      min_cost_flow.py OR-Tools SimpleMinCostFlow (capacity-aware)
    generators.py      five scenario profiles on Kolkata-metro land hubs (seeded)
    engine.py          run one algorithm / a comparison / the two-phase hybrid
    store.py           in-memory scenario store
    main.py            FastAPI app + endpoints
  tests/               cost, strategy-correctness, hybrid, and API tests (166)
  benchmarks/          profile comparison + solve-time scaling study

frontend/
  src/
    types/             TS mirrors of the backend models + per-algo labels/colours
    api/client.ts      typed fetch wrapper (/api -> :8000 via Vite proxy)
    components/
      ControlPanel     shared sidebar (scenario + weight sliders + run)
      AlgorithmPage    single-algorithm page (hero + stats + map + detail)
      ComparePage      all-algorithms page (dashboard + grid + focus map)
      HybridLab        two-phase hybrid page (pick primary+secondary, verdict)
      SimulatorPage    multi-scenario lab (pick profiles, per-profile breakdown)
      AlgoStats        headline stat cards (with hover ⓘ descriptions)
      MapView          Leaflet/OSM map (truck icons, package/pin markers, split routes)
      ComparisonGrid   side-by-side mini-maps
      MetricsDashboard callouts + objective chart + metric matrix
      ExplanationDrawer per-decision drawer (breakdown, runner-up, rejections)
    styles/theme.css   modern dispatch-console design system
    App.tsx            tab navigation + shared state + per-tab orchestration
```

---

## End-to-end flow — what happens when you change anything

This is the single most useful thing to internalise. Changing the scenario or weights (or
switching tabs) triggers this chain; every box is a real file you can open.

The app always does two things: (1) **generate the scenario** from `(profile, counts, seed)`,
then (2) **allocate** — and *which* allocate call depends on the active tab:

- **single-algorithm tab** → `POST /allocate/compare` with `[thatAlgo, hungarian]` (running it
  alongside Hungarian fills in its optimality gap for free),
- **Compare All tab** → `POST /allocate/compare` with every selected algorithm,
- **Hybrid Lab tab** → `POST /allocate/hybrid` (plus each component alone, for the comparison).

The diagram below traces the *Compare All* path; the other two differ only in that final call.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ BROWSER (React)                                                                         │
│                                                                                        │
│  ControlPanel ──(profile, n_trucks, n_orders, seed, algos[], weights)──► App.run()     │
│        │                                                                                │
│        │ 1. api.generate(profile, nTrucks, nOrders, seed)                              │
│        │ 2. api.compare(scenario.id, selected, weights)                                │
│        ▼                                                                                │
│  api/client.ts  ── fetch("/api/...") ──┐                                               │
└────────────────────────────────────────┼──────────────────────────────────────────────┘
                                          │  Vite dev server rewrites /api/* → :8000
                                          ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ BACKEND (FastAPI · app/main.py)                                                         │
│                                                                                        │
│  POST /scenarios/generate ─► generators.generate_scenario(profile, …, seed)            │
│        │   builds a deterministic Scenario(trucks[], orders[], decision_time, weights) │
│        │   store.put(scenario)            (in-memory dict, keyed by scenario.id)       │
│        ▼                                                                                │
│  POST /allocate/compare ─► engine.run_comparison(scenario, algorithms, weights)        │
│        │                                                                                │
│        │   for each algorithm:  engine.run_algorithm(...)                              │
│        │       ├─ cost.build_cost_matrix(trucks, orders, decision_time, weights)        │
│        │       │     → for every (truck,order): hard-constraint gate, then soft cost    │
│        │       │     → CostMatrix (NxM numpy array, +inf at infeasible cells)           │
│        │       ├─ strategy.allocate(cost_matrix)        ← the ONLY part that differs    │
│        │       │     ├─ strategy.solve(cm) → [(truck_idx, order_idx), …]               │
│        │       │     └─ explain.build_assignment(...) per pair → Assignment+Explanation │
│        │       └─ metrics.compute_metrics(...) → Metrics (coverage, cost, on-time, …)   │
│        │                                                                                │
│        │   then: fill optimality_gap of every result vs the Hungarian baseline         │
│        ▼                                                                                │
│  CompareResult { scenario_id, results: { greedy:…, hungarian:…, … } }  ──JSON──►        │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ BROWSER renders the response                                                            │
│   MetricsDashboard  ── headline callouts + objective bar chart + metric matrix          │
│   ComparisonGrid    ── one mini-map per algorithm (side-by-side)                        │
│   MapView (focus)   ── large interactive map; click a route ▼                           │
│   ExplanationDrawer ── cost breakdown + runner-up truck + rejected-truck reasons        │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### The flow in words

1. **You configure a scenario** in the `ControlPanel`: a *profile* (e.g. `contested`), how
   many trucks/orders, a *seed*, and the *cost weights*. The active **tab** decides which
   algorithm(s) run.
2. **`App.tsx`** ([`frontend/src/App.tsx`](./frontend/src/App.tsx)) regenerates the scenario
   when its inputs change, then a keyed effect calls the right endpoint for the active tab
   through the typed wrapper [`api/client.ts`](./frontend/src/api/client.ts): `generate` to
   build the scenario, then `compare` or `hybrid` to allocate. Changing only the weights
   re-allocates without regenerating the scenario.
3. **`/scenarios/generate`** calls [`generators.py`](./backend/app/generators.py), which
   builds a **deterministic** `Scenario` from `(profile, seed)` — same seed ⇒ identical
   trucks and orders, every time — and stores it in the in-memory
   [`store`](./backend/app/store.py) keyed by `scenario.id`.
4. **`/allocate/compare`** drives [`engine.run_comparison`](./backend/app/engine.py). For
   **each** algorithm it runs `run_algorithm`, which does three things in strict order:
   - **Build the cost matrix once** ([`cost.build_cost_matrix`](./backend/app/cost.py)).
     Every `(truck, order)` cell first passes a **hard-constraint gate** (capability,
     weight, volume, idle status, shift window, can-finish-before-shift-end). Pass ⇒ a
     **soft cost** `w_dist·km + w_late·lateness + w_idle·idle − w_prio·priority`. Fail ⇒
     the cell is `+∞` and can never be chosen. *This shared matrix is why the comparison is
     fair — all algorithms see exactly the same costs; only their search differs.*
   - **Run the strategy** ([`strategies/*.py`](./backend/app/strategies/)). Each strategy's
     `solve(cost_matrix)` returns chosen `(truck, order)` index pairs; the shared
     `allocate()` then turns each pair into a fully **explained `Assignment`** via
     [`explain.build_assignment`](./backend/app/explain.py).
   - **Compute metrics** ([`metrics.compute_metrics`](./backend/app/metrics.py)) — the same
     set for every algorithm.
5. **The optimality gap is filled in** by comparing every result's `objective` against the
   **Hungarian** baseline (the provable one-to-one optimum). A negative gap means an
   algorithm beat one-to-one Hungarian (how Min-Cost Flow wins the `batching` profile).
6. **The browser renders** the `CompareResult`: dashboard, side-by-side mini-maps, a large
   focus map, and — when you click any route — the per-decision explanation drawer.

> **Single-call path:** the UI uses `/allocate/compare`, but `/allocate` runs exactly one
> algorithm with the same pipeline (steps 4a–4c) if you want to drive it directly from
> Swagger or `curl`.

### Backend module responsibilities (the order data flows through them)

| # | Module | Responsibility | Key output |
| --- | --- | --- | --- |
| 1 | [`models.py`](./backend/app/models.py) | Pydantic domain types — the contract for everything | `Truck`, `Order`, `Scenario`, `Assignment`, `Metrics` |
| 2 | [`generators.py`](./backend/app/generators.py) | Synthesise deterministic scenarios by profile + seed | `Scenario` |
| 3 | [`store.py`](./backend/app/store.py) | Persist/fetch scenarios (`Store` interface, in-memory impl) | — |
| 4 | [`cost.py`](./backend/app/cost.py) | **Hard-constraint gate + soft-cost matrix** (shared by all) | `CostMatrix` (+ per-cell `CellDetail`) |
| 5 | [`strategies/*.py`](./backend/app/strategies/) | The three searches over the matrix | `[(truck_idx, order_idx)]` |
| 6 | [`explain.py`](./backend/app/explain.py) | Turn raw pairs into explained assignments | `Assignment` + `Explanation` |
| 7 | [`metrics.py`](./backend/app/metrics.py) | Same metrics for every algorithm | `Metrics` |
| 8 | [`engine.py`](./backend/app/engine.py) | Orchestrate 4→7, fill optimality gap, run the hybrid | `AllocationResult` / `CompareResult` |
| 9 | [`main.py`](./backend/app/main.py) | FastAPI routes + request validation + CORS | JSON responses |

### Frontend component responsibilities

| Component | Role |
| --- | --- |
| [`App.tsx`](./frontend/src/App.tsx) | Tab navigation + shared scenario state; regenerates the scenario and runs the active tab's endpoint (auto-runs on change) |
| [`ControlPanel`](./frontend/src/components/ControlPanel.tsx) | Shared sidebar: scenario profile, counts, seed, weight sliders, Run; hosts the algorithm toggles on the Compare tab |
| [`AlgorithmPage`](./frontend/src/components/AlgorithmPage.tsx) | One algorithm's page: hero header, stat cards, large map, decision-detail panel |
| [`ComparePage`](./frontend/src/components/ComparePage.tsx) | Compare-All page: dashboard + comparison grid + switchable focus map |
| [`HybridLab`](./frontend/src/components/HybridLab.tsx) | Two-phase hybrid: primary/secondary pickers, verdict, combined-vs-alone table, map |
| [`SimulatorPage`](./frontend/src/components/SimulatorPage.tsx) | Multi-scenario lab: pick profiles → per-profile summary cards → click for full breakdown |
| [`AlgoStats`](./frontend/src/components/AlgoStats.tsx) | Six headline stat cards for a single result |
| [`MetricsDashboard`](./frontend/src/components/MetricsDashboard.tsx) | Headline callouts + objective bar chart + best/worst-highlighted metric matrix |
| [`ComparisonGrid`](./frontend/src/components/ComparisonGrid.tsx) | One mini-map per algorithm, side-by-side |
| [`MapView`](./frontend/src/components/MapView.tsx) | Leaflet/OSM map: **truck icons** (bright = working), **package** pickups (sized by priority, red+pulsing = unassigned), **pin** dropoffs, split routes (dashed empty leg + solid loaded leg), rich hover snippets |
| [`ExplanationDrawer`](./frontend/src/components/ExplanationDrawer.tsx) | Per-decision panel opened by clicking a route |
| [`api/client.ts`](./frontend/src/api/client.ts) · [`types/index.ts`](./frontend/src/types/index.ts) | Typed fetch wrapper + TS mirrors of the backend models |

---

### Key design choice — one bipartite cost matrix per cycle

Each allocation run is modelled as a **bipartite assignment for one dispatch cycle**: every
truck takes at most one order (or up to `capacity_orders` for the batching profile). This is
deliberate — it keeps Greedy and Hungarian directly comparable on identical inputs
and gives Hungarian a provable optimum to serve as the baseline. Full multi-stop vehicle
routing (VRP) is out of scope by design; the rationale is in `SYSTEM_DESIGN.md`.

### Objective and the optimality gap

```
objective = total_assignment_cost + w_unassigned · (number of unserved orders)
```

The unassigned penalty is **uniform** (per order, not priority-weighted) on purpose: at equal
coverage the objective reduces to total cost, so the gap is monotonic and the cost-optimal
methods can't be "beaten" by an algorithm that merely served cheaper orders. Priority is a
genuinely competing goal, so it's reported on its own as `priority_weighted_fulfilment`. The
**optimality gap** is each algorithm's objective relative to the Hungarian baseline; a
*negative* gap means an algorithm beat one-to-one Hungarian by serving more orders (this is
how Min-Cost Flow wins the batching profile).

---

## API reference

All endpoints are served by FastAPI (`app/main.py`). **Live, always-current docs** (try requests
in the browser): **Swagger UI at <http://localhost:8000/docs>**, OpenAPI JSON at
<http://localhost:8000/openapi.json>. Algorithm keys: `greedy`, `hungarian`, `min_cost_flow`.
Errors: **404** unknown scenario, **422** unknown algorithm or invalid body.

| # | Method | Path | Body → Response |
| --- | --- | --- | --- |
| 1 | `GET` | `/` | — → `{service, docs, algorithms[]}` (health/info) |
| 2 | `GET` | `/algorithms` | — → `AlgorithmInfo[]` (key, name, optimality, model, complexity, best_when) |
| 3 | `POST` | `/scenarios/generate` | `{profile, n_trucks, n_orders, seed, name?}` → `Scenario` |
| 4 | `POST` | `/scenarios` | `Scenario` (explicit trucks/orders) → `Scenario` (id assigned if blank) |
| 5 | `GET` | `/scenarios` | — → `string[]` (scenario ids) |
| 6 | `GET` | `/scenarios/{id}` | — → `Scenario` |
| 7 | `POST` | `/scenarios/{id}/trucks` | `Truck` → updated `Scenario` |
| 8 | `POST` | `/scenarios/{id}/orders` | `Order` → updated `Scenario` |
| 9 | `POST` | `/allocate` | `{scenario_id, algorithm, weights?}` → `AllocationResult` |
| 10 | `POST` | `/allocate/compare` | `{scenario_id, algorithms[], weights?}` → `CompareResult` (+ optimality gap) |
| 11 | `POST` | `/allocate/hybrid` | `{scenario_id, primary, secondary, weights?}` → `AllocationResult` (two-phase) |

**Core response shapes** (full field lists in [`backend/app/models.py`](./backend/app/models.py) and
their TS mirrors in [`frontend/src/types/index.ts`](./frontend/src/types/index.ts)):

- `AllocationResult` = `{ algorithm, assignments: Assignment[], unassigned_order_ids: string[], metrics: Metrics }`
- `Assignment` = `{ truck_id, order_id, cost, eta, predicted_lateness_min, travel_km, explanation }`
- `Explanation` = `{ breakdown{distance,lateness,idle,priority}, runner_up_truck_id, runner_up_cost, runner_up_delta, rejected[], note }`
- `Metrics` = `{ coverage, total_cost, objective, optimality_gap, total_travel_km, avg_travel_km, on_time_rate, avg_lateness_min, max_lateness_min, fleet_utilisation, load_balance_cv, priority_weighted_fulfilment, solve_ms, … }`
- `CompareResult` = `{ scenario_id, results: { <algorithm>: AllocationResult } }`
- `CostConfig` (the `weights` object) = `{ w_dist, w_late, w_idle, w_prio, w_unassigned, circuity_factor }`

**Typical flow with `curl`:**

```bash
# 1) generate a scenario (deterministic for a given seed)
SID=$(curl -s -X POST localhost:8000/scenarios/generate \
  -H 'Content-Type: application/json' \
  -d '{"profile":"batching","n_trucks":8,"n_orders":12,"seed":7}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')

# 2) run one algorithm
curl -s -X POST localhost:8000/allocate \
  -H 'Content-Type: application/json' \
  -d "{\"scenario_id\":\"$SID\",\"algorithm\":\"hungarian\"}"

# 3) compare several (fills optimality_gap vs Hungarian)
curl -s -X POST localhost:8000/allocate/compare \
  -H 'Content-Type: application/json' \
  -d "{\"scenario_id\":\"$SID\",\"algorithms\":[\"greedy\",\"hungarian\",\"min_cost_flow\"]}"

# 4) two-phase hybrid: primary solves all, secondary fills the leftovers
curl -s -X POST localhost:8000/allocate/hybrid \
  -H 'Content-Type: application/json' \
  -d "{\"scenario_id\":\"$SID\",\"primary\":\"hungarian\",\"secondary\":\"greedy\"}"

# optional: override cost weights on any allocate call
#   ... -d '{"scenario_id":"...","algorithm":"greedy","weights":{"w_dist":2,"w_late":5,"w_idle":5,"w_prio":8,"w_unassigned":100,"circuity_factor":1.3}}'
```

---

## Tech & licensing

All open-source, no keys, no paid services: FastAPI, Pydantic, NumPy, SciPy, OR-Tools,
React, Vite, react-leaflet, Leaflet, Recharts. Map tiles are CARTO basemaps over
OpenStreetMap data.
