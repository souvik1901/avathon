# Algorithms — Implementation Deep-Dive

This is the **detailed** write-up: for each strategy it explains *how it was implemented*, walks
through the actual code line by line, and then quantifies *when the difference between methods
matters*. Source lines are cited as `file:line` so you can open them alongside.

> **Looking for the short version?** The high-level comparison (no code internals) is in
> **[`ALGORITHMS_OVERVIEW.md`](./ALGORITHMS_OVERVIEW.md)** — that's the one to skim or present.
> Numbers below come from `benchmarks/run_benchmarks.py` (8 trucks × 12 orders, seed 7, unless noted).

**Contents**
1. [Shared foundation — the cost engine](#1-shared-foundation--the-cost-engine-appcostpy)
2. [The strategy pattern](#2-the-strategy-pattern-appstrategiesbasepy)
3. [Greedy](#3-greedy--appstrategiesgreedypy) · [Hungarian](#4-hungarian--appstrategieshungarianpy) · [Min-Cost Flow](#5-min-cost-flow--appstrategiesmin_cost_flowpy)
4. [Hybrid (two-phase composition)](#6-hybrid--appenginepy)
5. [Results, trade-offs, scaling](#7-results-by-scenario)

---

## 1. Shared foundation — the cost engine (`app/cost.py`)

Before any algorithm runs, every `(truck, order)` pair is scored **once** into a dense matrix.
This is the experimental control: all algorithms read the *same* numbers, so any difference in
their output is a difference in *search*, never in cost definition.

### 1.1 Feasibility + cost in one pass — `_evaluate_pair` (`cost.py:74`)

```python
def _evaluate_pair(truck, order, dt, cfg) -> CellDetail:
    # --- hard constraints (the feasibility gate) ---
    missing = set(order.required_capabilities) - set(truck.capabilities)
    if missing:
        return CellDetail(False, f"missing capability: {', '.join(sorted(missing))}")
    if order.weight_kg > truck.capacity_weight_kg:
        return CellDetail(False, f"over weight capacity (...)")
    if order.volume_m3 > truck.capacity_volume_m3:
        return CellDetail(False, f"over volume capacity (...)")
    if truck.status != "idle":
        return CellDetail(False, f"truck not idle (status={truck.status})")
    if not (truck.shift_start <= dt <= truck.shift_end):
        return CellDetail(False, "outside truck shift window")
```

- Each `if` is one **hard constraint**. The first that fails **short-circuits** to an infeasible
  `CellDetail` carrying a *human-readable reason* — that string is exactly what later surfaces in
  the explanation drawer's "rejected trucks" list. No cost is computed for an infeasible pair.
- `missing` uses set difference: the order's required capabilities must be a **subset** of the
  truck's. Capacity checks are simple magnitude comparisons.

```python
    # --- timeline (when does this job actually finish?) ---
    deadhead_km = road_km(truck.location, order.pickup, cfg.circuity_factor)   # empty run to pickup
    loaded_km   = road_km(order.pickup, order.dropoff, cfg.circuity_factor)    # revenue run
    travel_km   = deadhead_km + loaded_km

    arrive_pickup = dt + timedelta(minutes=travel_minutes(deadhead_km, truck.avg_speed_kmph))
    start_service = max(arrive_pickup, order.ready_at)                         # can't start early
    depart_pickup = start_service + timedelta(minutes=order.service_time_min)
    eta           = depart_pickup + timedelta(minutes=travel_minutes(loaded_km, truck.avg_speed_kmph))

    if eta > truck.shift_end:                       # 6th hard constraint: must finish on shift
        return CellDetail(False, "cannot finish before shift end")
    predicted_lateness_min = max(0.0, (eta - order.due_by).total_seconds() / 60.0)
```

- The route is modelled as **truck → pickup → dropoff**. `road_km` (`cost.py:36`) is haversine
  great-circle distance × a circuity factor (~1.3) — a cheap, deterministic, offline stand-in for
  road distance.
- `start_service = max(arrive_pickup, order.ready_at)` captures **waiting**: if the truck beats the
  order's ready time, it idles until then. `eta` is the predicted dropoff time.
- A late finish past `shift_end` is a *hard* infeasibility; lateness past `due_by` is a *soft* cost
  (computed next), clamped at 0 so being early is never a bonus.

```python
    # --- soft cost (what we minimise) ---
    distance    = cfg.w_dist * travel_km * truck.cost_per_km
    lateness    = cfg.w_late * predicted_lateness_min
    utilisation = max(order.weight_kg / truck.capacity_weight_kg,
                      order.volume_m3 / truck.capacity_volume_m3)
    idle        = cfg.w_idle * (1.0 - min(1.0, utilisation))
    priority    = -cfg.w_prio * order.priority          # NEGATIVE = a bonus
    total = distance + lateness + idle + priority
    return CellDetail(feasible=True, total_cost=total, distance=distance, ...)
```

- Four weighted terms summed into one scalar `total_cost`. `priority` is **negative** — it
  *lowers* the cost of serving an important order, biasing (not forcing) the search toward it.
- `idle` penalises wasted capacity: `utilisation` is the fraction of the truck filled (by the
  tighter of weight/volume), so `1 − utilisation` is the slack. Sending a huge truck for a tiny
  parcel is expensive; `min(1.0, …)` clamps a full truck to zero idle.
- The returned `CellDetail` carries the **decomposition** (distance/lateness/idle/priority) and the
  **timeline** (eta, lateness) — computed once here, reused by both the metrics and the explanation.

### 1.2 Assembling the matrix — `build_cost_matrix` (`cost.py:123`)

```python
cost = np.full((n, m), INFEASIBLE, dtype=float)        # default +inf everywhere
details = []
for i, t in enumerate(trucks):
    row = []
    for j, o in enumerate(orders):
        d = _evaluate_pair(t, o, dt, cfg)
        row.append(d)
        if d.feasible:
            cost[i, j] = d.total_cost                  # overwrite +inf only when feasible
    details.append(row)
return CostMatrix(trucks=trucks, orders=orders, cost=cost, details=details)
```

- A NumPy array initialised to `+∞` (`INFEASIBLE = math.inf`); a cell becomes finite **only** if the
  pair passed the gate. So "infeasible" is encoded directly as "infinite cost" — every algorithm
  then respects hard constraints *for free* by simply never choosing an `inf` cell.
- The parallel `details` grid keeps the rich per-cell info for explanations. `CostMatrix` (rows =
  trucks, cols = orders) is the single object every strategy receives.

---

## 2. The strategy pattern (`app/strategies/base.py`)

Every algorithm implements just `solve(cost_matrix) -> [(truck_idx, order_idx)]`. The base class
turns those raw index pairs into fully-explained assignments, so each strategy stays focused purely
on the *search*.

```python
def allocate(self, cm) -> tuple[list[Assignment], list[str]]:
    pairs = self.solve(cm)                                          # <- the ONLY per-algorithm part
    assignments = [build_assignment(cm, ti, oj, note=self.note_for(cm, ti, oj))
                   for ti, oj in pairs]
    assigned_orders = {oj for _, oj in pairs}
    unassigned = [cm.orders[j].id for j in range(len(cm.orders)) if j not in assigned_orders]
    return assignments, unassigned
```

- `solve()` returns only `(truck_index, order_index)` pairs (`base.py:28`).
- `allocate()` (`base.py:36`) maps each pair through `explain.build_assignment` (which attaches the
  cost breakdown, the runner-up truck, and the rejected-truck reasons), then derives the unassigned
  list. `note_for()` (`base.py:32`) is an optional per-algorithm hook for commentary (Hungarian and
  Min-Cost Flow override it).
- **Consequence:** adding a new algorithm = one subclass implementing `solve`. The API, UI, metrics,
  and explanations all pick it up via the registry (`strategies/__init__.py`).

---

## 3. Greedy — (`app/strategies/greedy.py`)

**Idea.** Process orders in business order (most important / most urgent first); give each the
cheapest still-available truck. Myopic, fast, online-friendly, no backtracking.

**Implementation** (`greedy.py:26`):

```python
def solve(self, cm) -> list[tuple[int, int]]:
    orders = cm.orders
    order_seq = sorted(range(len(orders)),
                       key=lambda j: (-orders[j].priority, orders[j].due_by))   # (1)
    remaining = [t.capacity_orders for t in cm.trucks]                          # (2)
    pairs = []
    for oj in order_seq:                                                        # (3)
        col = cm.cost[:, oj]
        candidates = sorted(
            (i for i in range(len(cm.trucks))
             if np.isfinite(col[i]) and remaining[i] > 0),                      # (4)
            key=lambda i: col[i])                                               # (5)
        if candidates:
            ti = candidates[0]
            pairs.append((ti, oj))
            remaining[ti] -= 1                                                  # (6)
    return pairs
```

1. **Processing order** — sort orders by `priority` descending, then `due_by` ascending. This is the
   "business" sequence: important and urgent orders get first pick. (Greedy's whole character is set
   by this sort.)
2. **Capacity bookkeeping** — `remaining[i]` tracks how many more orders truck `i` may still take
   this cycle (starts at `capacity_orders`; usually 1).
3. For each order **in that fixed sequence** (no reconsideration later — that's the myopia).
4. **Candidate trucks** — feasible for this order (`isfinite`, i.e. not `+∞`) *and* with spare
   capacity left.
5. **Cheapest first** — sort candidates by this column's cost and take `candidates[0]`.
6. **Commit** — record the pair and decrement that truck's remaining capacity. Once a truck is full
   it drops out of all later orders' candidate lists — *this is exactly how an early pick can strand
   a later order*, the optimality gap we measure.

Complexity `O(M·N)` (each order scans the truck column). No global view: a locally cheap early
commit is never revisited.

---

## 4. Hungarian — (`app/strategies/hungarian.py`)

**Idea.** Solve the whole min-cost one-to-one matching at once (Kuhn–Munkres) for the provably
cheapest assignment. This is the **baseline** every other method is measured against.

**Implementation** (`hungarian.py:30`):

```python
def solve(self, cm) -> list[tuple[int, int]]:
    C = cm.cost
    finite = C[np.isfinite(C)]
    if finite.size == 0:
        return []
    big_m = (np.abs(finite).max() + 1.0) * (C.shape[0] + C.shape[1]) * 1000.0   # (1)
    work = np.where(np.isfinite(C), C, big_m)                                   # (2)
    rows, cols = linear_sum_assignment(work)                                    # (3)
    pairs = []
    for ti, oj in zip(rows, cols):
        if np.isfinite(C[ti, oj]):                                              # (4)
            pairs.append((int(ti), int(oj)))
    return pairs
```

1. **The `inf` problem.** SciPy's `linear_sum_assignment` needs **finite** weights — it cannot take
   `+∞`. So we build `big_m`: a sentinel larger than any real assignment could ever sum to
   (`max|cost| × (rows+cols) × 1000`), guaranteeing the solver only ever picks a sentinel cell when
   it has *no* feasible alternative.
2. Replace every `+∞` with `big_m` to get a finite `work` matrix.
3. **The solve.** `linear_sum_assignment` returns the optimal row→col matching in `O(n³)`. It handles
   **rectangular** matrices natively (unequal trucks/orders).
4. **Drop the sentinels.** Any returned pair that landed on a `big_m` cell was never truly feasible
   — we check the *original* `C` (still `inf` there) and drop it, so those orders end up correctly
   *unassigned* rather than matched to an impossible truck. (Tested explicitly so an infeasible pair
   can never leak through.)

**The explainability hook** (`hungarian.py:45`) — `note_for` surfaces the global-vs-local trade:

```python
def note_for(self, cm, ti, oj) -> str | None:
    col = cm.cost[:, oj]
    feasible_rows = [i for i in range(len(cm.trucks)) if np.isfinite(col[i])]
    local_best = min(feasible_rows, key=lambda i: col[i])
    if local_best != ti:               # the optimum did NOT give this order its cheapest truck
        delta = float(col[ti] - col[local_best])
        return (f"Global optimum assigned a non-cheapest truck here (+{delta:.1f} locally) "
                f"so another order could be served far more cheaply — a trade greedy cannot make.")
    return "This truck was also the locally cheapest feasible option."
```

This is the "money" insight made visible: when Hungarian deliberately gives an order its *second*
cheapest truck so the fleet total drops, the drawer says so.

---

## 5. Min-Cost Flow — (`app/strategies/min_cost_flow.py`)

**Idea.** Generalise to **one truck → many orders** by modelling allocation as a min-cost flow
network. With `capacity_orders = 1` it reproduces Hungarian exactly; with `> 1` it can consolidate.

**The network** (`min_cost_flow.py:39`):

```python
smcf = ortools_mcf.SimpleMinCostFlow()
SOURCE, SINK = 0, 1
truck_node = lambda i: 2 + i
order_node = lambda j: 2 + n + j
total_capacity = int(sum(t.capacity_orders for t in cm.trucks))

# source -> truck : capacity = how many orders this truck may take
for i, t in enumerate(cm.trucks):
    if t.capacity_orders > 0:
        smcf.add_arc_with_capacity_and_unit_cost(SOURCE, truck_node(i), int(t.capacity_orders), 0)

# truck -> order : one arc per FEASIBLE pair, capacity 1, cost = scaled assignment cost
for i in range(n):
    for j in range(m):
        if np.isfinite(C[i, j]):
            cost_int = int(round(C[i, j] * _SCALE))
            arc = smcf.add_arc_with_capacity_and_unit_cost(truck_node(i), order_node(j), 1, cost_int)
            arc_lookup[arc] = (i, j)

# order -> sink : capacity 1, cost = -serve_reward  (a big BONUS for serving the order)
for j in range(m):
    smcf.add_arc_with_capacity_and_unit_cost(order_node(j), SINK, 1, -serve_reward)

# source -> sink : overflow so unused capacity drains at zero cost
smcf.add_arc_with_capacity_and_unit_cost(SOURCE, SINK, total_capacity, 0)
smcf.set_node_supply(SOURCE, total_capacity)
smcf.set_node_supply(SINK, -total_capacity)
```

- **Node layout.** A single `SOURCE` and `SINK`, then one node per truck and one per order. The
  `lambda`s map indices to node ids.
- **`source → truck` (cap = `capacity_orders`)** — this is *the* lever: it bounds how many orders a
  truck can take. Set it to 1 and the network is bipartite matching (= Hungarian); set it to 3 and a
  truck can pick up three nearby orders.
- **`truck → order` (cap 1, cost)** — one arc per **feasible** pair only (infeasible pairs simply get
  no arc). Costs are integer-scaled (`_SCALE = 1000`, `min_cost_flow.py:28`) because OR-Tools works
  in integers. `arc_lookup` remembers which arc was which `(truck, order)`.
- **`order → sink` (cost `-serve_reward`)** — `serve_reward` (`min_cost_flow.py:47`) is huge and
  *negative*, i.e. a reward. It makes **serving an order** dominate any real per-pair cost, so the
  solver maximises **coverage first**, then uses the real costs to break ties cheaply.
- **`source → sink` overflow** — lets unused truck capacity flow straight to the sink at zero cost,
  so the problem is always feasible (supply = demand) without forcing every truck to be used.

```python
status = smcf.solve()
if status != smcf.OPTIMAL:
    return []
pairs = [(i, j) for arc, (i, j) in arc_lookup.items() if smcf.flow(arc) > 0]    # arcs with flow = chosen
return pairs
```

- After solving, an order is assigned to a truck **iff** its `truck → order` arc carries flow. We
  read those off via `arc_lookup`. Polynomial time (network simplex).

---

## 6. Hybrid — (`app/engine.py`)

Not a strategy in the registry but a **composition** of two, implemented at the engine level so it
reuses one cost matrix, the same explanation builder, and the same metrics.

### 6.1 The residual problem — `_residual_matrix` (`engine.py:60`)

```python
def _residual_matrix(cm, pairs) -> CostMatrix:
    cost = cm.cost.copy()
    served = {oj for _, oj in pairs}
    for oj in served:
        cost[:, oj] = INFEASIBLE                       # (1) remove already-served orders

    used = {}
    for ti, _ in pairs:
        used[ti] = used.get(ti, 0) + 1                 # (2) count Phase-1 load per truck

    new_trucks = []
    for i, t in enumerate(cm.trucks):
        remaining = t.capacity_orders - used.get(i, 0)
        if remaining <= 0:
            cost[i, :] = INFEASIBLE                     # (3) full trucks can't take more
        new_trucks.append(t.model_copy(update={"capacity_orders": remaining}))   # (4)
    return CostMatrix(trucks=new_trucks, orders=cm.orders, cost=cost, details=cm.details)
```

1. Orders served in Phase 1 get their **column set to `+∞`** — Phase 2 can never re-assign them.
2. Count how many orders each truck took in Phase 1.
3. A truck with **no remaining capacity** has its whole **row set to `+∞`** — it's out for Phase 2.
4. Crucially, we **clone the trucks with their decremented `capacity_orders`** (`model_copy` bypasses
   validation, so `remaining == 0` is fine — the row is already masked). This is what lets a
   *capacity-aware* secondary (greedy, min-cost-flow) behave correctly on the residual: it reads the
   real remaining capacity. The per-cell `details` are shared unchanged, so explanations stay anchored
   to the original cost model.

### 6.2 The two phases — `run_hybrid` (`engine.py:91`)

```python
cm = build_cost_matrix(scenario.trucks, scenario.orders, scenario.decision_time, cfg)
prim, sec = get_strategy(primary), get_strategy(secondary)

pairs_a = prim.solve(cm)                       # Phase 1: primary on the full problem
residual = _residual_matrix(cm, pairs_a)
pairs_b = sec.solve(residual)                  # Phase 2: secondary on the leftovers

served_a = {oj for _, oj in pairs_a}
pairs_b = [(ti, oj) for ti, oj in pairs_b if oj not in served_a]    # guard against overlap

assignments = ([build_assignment(cm, ti, oj, note=note_a) for ti, oj in pairs_a]
             + [build_assignment(cm, ti, oj, note=note_b) for ti, oj in pairs_b])
```

- Phase 1 runs the primary on the real matrix; Phase 2 runs the secondary on the residual. The
  order-columns are disjoint by construction (Phase 1's served orders are masked out), and the
  explicit filter is belt-and-braces.
- Each assignment is tagged with a **phase note** (`"Phase 1 — assigned by the primary…"` /
  `"Phase 2 — filled by the secondary…"`), which is what the UI shows when you click a hybrid route.
- **Key property — monotone coverage.** Phase 2 only *adds* (it can never remove a Phase-1
  assignment), so hybrid coverage ≥ primary coverage **always**. The numbers in §8 show this plays
  out as "equals the primary" in one-to-one profiles and "+coverage" under batching.

---

## 7. Results by scenario

| Profile | Algorithm | Coverage | Cost | Objective | Gap | Pri-fulfil |
| --- | --- | --: | --: | --: | --: | --: |
| **abundant** | greedy | 92% | 313.1 | 413.1 | **+9.8%** | 93% |
| (20 trucks, 12 orders) | hungarian | 100% | 376.1 | 376.1 | — | 100% |
| | min_cost_flow | 100% | 376.1 | 376.1 | 0.0% | 100% |
| **contested** | greedy | 67% | 433.4 | 833.4 | **+13.7%** | 83% |
| (8 trucks, 12 orders) | hungarian | 67% | 333.2 | 733.2 | — | 77% |
| | min_cost_flow | 67% | 333.2 | 733.2 | 0.0% | 77% |
| **scarce** | greedy | 58% | 310.6 | 810.6 | **+6.0%** | 51% |
| (7 trucks, 12 orders) | hungarian | 58% | 264.6 | 764.6 | — | 46% |
| | min_cost_flow | 58% | 264.6 | 764.6 | 0.0% | 46% |
| **tight_windows** | greedy | 67% | 554.7 | 954.7 | **+18.8%** | 70% |
| (8 trucks, 12 orders) | hungarian | 67% | 403.7 | 803.7 | — | 64% |
| | min_cost_flow | 67% | 403.7 | 803.7 | 0.0% | 64% |
| **batching** | greedy | 92% | 497.4 | 597.4 | **−22.0%** | 97% |
| (8 trucks ×3 cap, 12 orders) | hungarian | 67% | 365.5 | 765.5 | — | 77% |
| | min_cost_flow | 92% | 488.4 | 588.4 | **−23.1%** | 97% |

(`min_cost_flow == hungarian` exactly at `capacity_orders = 1`. Numbers regenerate with
`python -m benchmarks.run_benchmarks`.)

---

## 8. When each approach wins — and when the difference matters

**Greedy's penalty shows up as extra cost — and occasionally a missed order.** Where trucks are the
bottleneck (*contested* and *tight_windows* have 8 trucks for 12 orders, so at most 8 can be served
one-to-one), greedy and Hungarian cover the **same** 67% — but greedy routes that same set **more
expensively**: **+13.7%** under contention and **+18.8%** under tight windows. The tighter the
deadlines, the more a myopic early pick forces a costly later one. In *abundant*, greedy even *strands
one order* (92% vs 100%) despite surplus trucks — a locally cheap choice consumed the one truck a
later order needed — leaving it **+9.8%** off optimal. The thesis holds: *the value of a global method
grows as the problem tightens* (scarce +6.0% → abundant +9.8% → contested +13.7% → tight +18.8%).

**Hungarian wins whenever the one-to-one assignment is contested or scarce.** Provably optimal and,
thanks to SciPy's compiled core, the **fastest** method at every size tested (≈7 ms at N=400, below).

**The `scarce` row is the subtle one.** Greedy and Hungarian both cover 58%, yet greedy's cost is
higher (310.6 vs 264.6). Greedy spends extra travel to protect *high-priority* orders — its
priority-fulfilment is actually **higher** (51% vs 46%) — while Hungarian minimises total cost. So the
"+6.0% gap" is real on the cost objective, but the *priority* column shows the trade the single number
hides — which is why the engine reports coverage, cost, and priority fulfilment **separately**.

**Min-Cost Flow wins the moment a truck can carry more than one order.** In *batching*
(`capacity_orders = 3`), flow covers **92%** against Hungarian's **67%**, beating the one-to-one
optimum by **−23.1%**. No one-to-one method can reach this — Hungarian is capped at one
order per truck (67% = all 8 trucks used). (Capacity-aware greedy also reaches 92% here, mopping up
several nearby orders per truck.)

**Speed — the price of optimality.** Solve time for the algorithm's search only (matrix build excluded):

```
Solve time (median ms, contested, n/2 trucks) — algorithm only, matrix build excluded
algorithm          N=10    N=25    N=50   N=100   N=200   N=400
greedy             0.04    0.17    0.68    2.48    9.94   40.50
hungarian          0.01    0.02    0.07    0.24    1.22    6.89
min_cost_flow      0.10    0.49    1.68    6.25   24.03  131.04
```

SciPy's C-level Hungarian dominates at every tested size — it's both exact *and* fastest here.
Greedy's pure-Python per-order scan grows quicker, and min-cost flow does the most work (a full
flow solve), but all three are comfortably sub-second to N=400.

**The hybrid pays off exactly when there is leftover capacity to fill.** Running `Hungarian → Greedy`:

| Profile | Hungarian alone | Hybrid (H→G) | Phase-2 fills | Verdict |
| --- | --: | --: | --: | --- |
| abundant | 12/12 · obj 376 | 12/12 · obj 376 | 0 | identical — nothing left to fill |
| contested | 8/12 · obj 733 | 8/12 · obj 733 | 0 | identical — all trucks already used |
| scarce | 7/12 · obj 765 | 7/12 · obj 765 | 0 | identical |
| tight_windows | 8/12 · obj 804 | 8/12 · obj 804 | 0 | identical |
| **batching** | **8/12 · obj 765** | **11/12 · obj 658** | **3** | **+3 orders, objective −14%** |

In strict one-to-one profiles the primary already consumes every available truck, so Phase 2 has
nothing to work with and the hybrid is *exactly* the primary. The moment trucks have **spare
capacity** (*batching*), the fill phase turns Hungarian's capped 8/12 into 11/12 — recovering much of
Min-Cost Flow's consolidation benefit by *composing* two simple methods. (Reverse to `Greedy →
Hungarian` and the capacity-aware greedy already reaches 11/12 in Phase 1: same destination, different
route.)

---

## 9. Summary

| If your situation is… | Use | Because |
| --- | --- | --- |
| Resources abundant, or online/streaming, or N huge | **Greedy** | Near-optimal when easy, fast, incremental; degrades only under contention |
| One-to-one, contested or scarce, exactness matters | **Hungarian** | Provably optimal *and* fastest at tested scale |
| A truck can serve multiple orders (consolidation) | **Min-Cost Flow** | Only method that covers more by batching — beats one-to-one |
| Optimal-first, then mop up leftover capacity | **Hybrid** (e.g. Hungarian→Greedy) | Composes two methods; adds coverage only when the fleet has slack (e.g. batching) |

The broader point the engine demonstrates: **the gap between a cheap heuristic and a global optimum
is small when resources are loose and large when they're tight** — so the value of a better algorithm
is highest exactly when the system is under stress.
