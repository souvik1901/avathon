# Decision Rationale — Personal Reference (NOT a deliverable)

> **This file is for you.** It is git-ignored and not part of the submission. Its job is to let
> you explain, in your own words, **why this system was built the way it was** and **why the
> obvious alternatives were rejected** — because the evaluation is of your *decision-making*,
> not just the working code.
>
> Format: each section is a decision, the reasoning, the alternatives considered, and a
> one-liner you can say out loud. Read §0 first, then skim the rest; the **"Say this"** lines
> are your quick-recall cues.

---

## 0. The 30-second story (memorise this shape)

> "It's a delivery-fleet allocation engine. I model each dispatch as a **bipartite assignment
> problem** for one time window — trucks to orders, at most one each. Every algorithm scores
> pairs through **one shared cost model** (hard constraints gate feasibility, soft costs rank
> the rest), so the *only* difference between algorithms is how they *search*. That makes the
> comparison fair. I built three: **Greedy** (myopic baseline), **Hungarian** (provably optimal
> one-to-one — my baseline to measure against), and **Min-Cost Flow** (the capacitated
> generalisation — a truck can batch several orders), plus a two-phase **Hybrid** that composes
> two of them. The headline finding: **the gap between a cheap heuristic and the global optimum
> is small when resources are loose and large when they're tight** — so a better algorithm is
> worth most exactly when the system is under stress."

Everything below is the defence of each clause in that paragraph.

---

## 1. Why the delivery-fleet domain (and not field service / healthcare / equipment)

**Decision:** Delivery fleet — trucks → pickup/dropoff orders.

**Why:** All four candidate domains in the brief reduce to the *same* mathematical core
(assign mobile resources to located, time-bound requests). Delivery fleet was chosen because:
- It has the **richest natural constraint set** that's still intuitive: weight/volume capacity,
  refrigerated/hazmat capabilities, shifts, time windows, priority. Easy to reason about, hard
  enough to be interesting.
- It makes the **batching** insight concrete and visual (a van picking up several nearby small
  parcels) — which is what justifies the min-cost-flow strategy.
- It maps cleanly to a **map UI** (real lat/lon, routes you can see).

**Alternatives & why not:**
- *Healthcare (staff → visits)* — same math but capacity/volume don't apply naturally; fewer
  hard constraints to demonstrate.
- *Equipment rental* — resources are often *not* mobile per-cycle (they sit at a job site for
  days), which breaks the clean "one decision cycle" framing.

**Say this:** "They're isomorphic; I picked the one with the richest intuitive constraints and
the clearest visual story for batching."

---

## 2. Why model it as a one-cycle bipartite assignment (and not full VRP)

**Decision:** At a decision time `T`, assign each available truck to **at most one** open order.
Per-cycle bipartite matching, not multi-stop routing.

**Why:** This is the single most important modelling decision, and it's deliberate.
- The brief's *named* comparison is **greedy (one-by-one, local) vs batch (Hungarian, global)**.
  That comparison is **only well-defined on the assignment problem**. If I'd modelled full VRP,
  "Hungarian" wouldn't even apply and the comparison the brief asks for would dissolve.
- Full **VRP is NP-hard**. A heuristic-vs-heuristic comparison has **no optimal baseline** to
  measure an optimality gap against. The whole "how much did being greedy cost us?" number
  depends on having a *provable* optimum (Hungarian) to compare to.
- It's **realistic**: many production dispatch systems batch decisions into short time windows
  and solve assignment per window.

**Alternatives & why not:**
- *Full multi-stop VRP (OR-Tools routing)* — NP-hard, no clean optimal baseline, and it would
  drown the local-vs-global comparison in routing heuristics. **Named as the explicit next step**
  so it's clear I know it exists and chose to scope it out, not that I missed it.
- *Continuous / streaming assignment* — interesting but the greedy strategy already represents
  the online case; batching is what exposes the global-optimisation win.

**Say this:** "The assignment problem is the only framing where 'greedy vs optimal batch' is a
well-posed comparison with a provable baseline. VRP is the honest next step, and I named it."

**Likely pushback — "Isn't one-truck-one-order unrealistic?"**
Yes, which is exactly why **min-cost flow** is in the set: it relaxes that to one-truck-*many*
via `capacity_orders`. So I model the clean case for a fair comparison *and* the realistic case
to show I understand the domain.

---

## 3. Why one shared cost matrix (the fairness lever)

**Decision:** A single `CostMatrix` is built once per run from `(scenario, weights)`; every
algorithm consumes the *same* matrix. Feasibility + cost are computed together per cell.

**Why:** This is what makes the comparison **scientifically honest**. If each algorithm computed
its own costs, any difference in output could be a difference in *cost definition* rather than a
difference in *search quality* — and the comparison would be meaningless. By fixing the cost
model, the only independent variable is the algorithm.

**Why feasibility and cost together (not a separate `feasibility.py`):** a feasible cell needs
its cost computed anyway, and an infeasible cell is just `+∞`. Splitting them means walking the
N×M matrix twice for no benefit. The per-cell `CellDetail` (cost breakdown + ETA + lateness) is
computed once and reused three times: by the matrix, the metrics, and the explanation.

**Say this:** "Shared cost model = the only variable is search quality. That's the experimental
control."

---

## 4. The cost model choices

### 4.1 Hard vs soft constraints
**Decision:** Capability / capacity / availability / time-window are **hard** (→ `+∞`,
never assigned). Distance / lateness / idle / priority are **soft** (weighted sum, minimised).

**Why:** The brief explicitly asks for both. Hard = physical/contractual impossibilities (a
non-refrigerated truck *cannot* carry frozen goods). Soft = preferences you trade off. Encoding
infeasibility as `+∞` means every algorithm respects hard constraints **for free** — they just
never pick an infinite-cost cell.

### 4.2 Haversine × circuity factor (not real road distance)
**Decision:** Great-circle distance × ~1.3 to approximate road km.

**Why:** Free, deterministic, offline, zero dependencies — and **accurate enough for a
*comparison***. The algorithms are compared on the *same* distances, so even if haversine is off
from true road distance by a constant-ish factor, the *relative* ranking of algorithms is
unaffected. Precision here would add cost and risk (API keys, network, non-determinism) for no
change in the conclusion.

**Alternatives & why not:**
- *OSRM (local routing engine)* — true road distance, but it's a whole service to stand up; the
  brief says run locally with no paid services. **Named as the upgrade** so it's clearly a
  conscious trade, not ignorance.
- *Google/Mapbox distance APIs* — paid, need keys, violate the brief.

**Say this:** "Haversine is deterministic and offline, and since every algorithm sees the same
distances, road-accuracy doesn't change the *comparison*. OSRM is the named upgrade."

### 4.3 Priority as a negative cost (bonus), not a hard rule
**Decision:** `- w_prio · priority` lowers the cost of serving important orders.

**Why:** Priority should *bias* allocation, not *dictate* it — a priority-5 order 200 km away
shouldn't always beat a priority-4 order next door. Making it a soft term lets the weight slider
tune how much priority matters, and keeps it comparable across algorithms.

### 4.4 The objective and the **uniform** unassigned penalty (subtle but important)
**Decision:** `objective = total_assignment_cost + w_unassigned · n_unassigned`, where the
penalty is **per order, uniform — not priority-weighted**.

**Why this is the trickiest call:** I needed a single scalar to rank algorithms (the optimality
gap). If the unassigned penalty were priority-weighted, an algorithm could look "better" just by
serving cheaper/low-priority orders, and the gap could go non-monotonic. Keeping it uniform means
**at equal coverage the objective reduces to pure total cost** — so the gap is clean and
monotonic, and a cost-optimal method can never be beaten by cherry-picking. Priority *is* a real
competing goal, so I report it **separately** as `priority_weighted_fulfilment` instead of
corrupting the objective with it.

**Say this:** "Uniform penalty keeps the optimality gap monotonic; priority is a competing
objective so I report it on its own axis rather than folding it in."

---

## 5. The algorithms — why each is in the set, and what each *proves*

The set is chosen so each algorithm makes a *different point*. It's not four ways to do the same
thing; it's four positions on the optimality/scale/model spectrum.

### 5.1 Greedy — why include a deliberately weak method
**Proves:** the **baseline** the brief names ("process requests one-by-one, locally optimal").
It's the thing the optimality gap is measured *from*. It's also genuinely the *right* choice in
two real regimes: **online/streaming** arrivals (you can't wait to batch) and **abundant
resources** (local picks rarely collide). So it's not a strawman — it's the pragmatic default at
the easy end, and the foil that makes the global methods' value visible at the hard end.

**Say this:** "Greedy isn't a strawman — it's the correct answer when resources are loose or
decisions are online. It's also the reference the gap is measured from."

### 5.2 Hungarian — why this is *the* optimal one-to-one, and why SciPy
**Proves:** the **global optimum** for one-to-one assignment. This is the linchpin: without a
provable optimum there's no gap to report, no "best/worst" highlight, nothing to anchor the
comparison. Hungarian/Kuhn-Munkres solves the assignment problem exactly in `O(n³)`.

**Why SciPy `linear_sum_assignment`:** it's a battle-tested, C-level implementation — correct
and *fast* (fastest of the three at every tested size, because it's compiled). Re-implementing
Hungarian by hand would be error-prone and slower with zero upside.

**The one gotcha I handled:** SciPy needs **finite** weights, but infeasible cells are `+∞`. I
substitute a large finite sentinel (`BIG_M`) and **drop any matched pair that landed on a
sentinel** as genuinely unassigned. There's a dedicated test that an infeasible pair can never
leak through.

**Say this:** "Hungarian gives me the provable optimum to measure everything against; SciPy's
compiled solver is correct and the fastest option. The only trick is sentinel-and-drop for
infeasible cells."

### 5.3 Min-Cost Flow — why model as a flow network, and why OR-Tools
**Proves:** the **domain-insight generalisation** — a real truck carries *several* small orders.
This is the brief's "your own approach based on domain insight." One-to-one matching structurally
*cannot* express batching; min-cost flow can, by giving each truck node a capacity of
`capacity_orders`. With capacity 1 it **provably reduces to Hungarian** (there's an equivalence
test); with capacity >1 it covers *more* orders and beats the one-to-one optimum (negative gap).

**The model:** `source →(cap=capacity_orders)→ truck →(cap 1, cost)→ order →(cap 1, −reward)→
sink`, plus a zero-cost overflow arc. The big negative `SERVE_REWARD` on order→sink makes the
solver maximise coverage first, then real costs break ties to minimise spend.

**Why OR-Tools (not NetworkX):** OR-Tools `SimpleMinCostFlow` is a compiled, industrial
min-cost-flow solver — fast and robust on the integer-scaled network. NetworkX's pure-Python
`min_cost_flow` works but is markedly slower and would hurt the scaling study.

**Alternatives & why not:**
- *Just extend Hungarian* — you can't; the assignment problem is one-to-one by definition.
- *MILP/CP-SAT* — could express batching too, but is heavier, slower, and overkill when
  min-cost flow models the exact same relaxation in polynomial time with a clean network.

**Say this:** "Batching is structurally impossible in one-to-one matching, so I lift it to a flow
network. Capacity 1 recovers Hungarian exactly; capacity >1 is where it wins. OR-Tools because
it's a compiled flow solver."

### 5.4 Why I *removed* the Auction (Bertsekas) — scoping judgment
I originally built a fourth strategy, Bertsekas' **auction** (orders bid for trucks; contested
trucks get pricier until an equilibrium emerges). I later **cut it on purpose**, and the *reason*
is itself a decision worth defending:

- **It didn't change any conclusion.** The auction only reaches the *same* optimum as Hungarian, by
  a different mechanism (pricing / dual ascent). On every scenario its row in the table was
  identical to Hungarian — so it added a fourth thing to explain without teaching anything new.
- **Its one selling point — parallelism — couldn't be shown here.** The auction's real-world draw is
  that independent bids parallelise at huge/distributed scale. But the project runs **serial, pure
  Python, small N**, where it was simply the *slowest* method. Demoing an algorithm whose advantage
  your own setup can't exhibit invites a confusing tangent.
- **Focus beats breadth in an interview.** Three methods that each make a *distinct* point — a fast
  heuristic (greedy), the provable optimum (Hungarian), and the capacitated generalisation
  (min-cost flow) — tell the whole story. A near-duplicate of the optimum dilutes it.

**Say this:** "I built the auction, then removed it. It only re-derived Hungarian's optimum by a
different route, and its real advantage — parallelism at scale — can't show in a serial Python
benchmark. Cutting it kept the comparison sharp: heuristic vs. provable optimum vs. capacitated
generalisation, each making a different point. Knowing what to *leave out* is part of the design."

> *(If pressed on the auction itself:* it's a dual-ascent view of the same assignment problem,
> near-optimal within `n·ε`; I square-padded the matrix so the unbalanced case converged. Happy to
> talk through it, but I scoped it out of the final build.)*

### 5.5 What I deliberately did *not* build
- **ML-based allocation (brief option):** no training data, would be a black box, and can't give
  the **provable optimality** or **per-decision explanation** the brief asks for. Wrong tool —
  this is a combinatorial optimisation problem with exact methods available, not a learning
  problem. *Say this:* "No labels, no explainability, no optimality guarantee — exact methods
  dominate here."
- **Genetic algorithms / simulated annealing:** metaheuristics with no optimality guarantee and
  worse explainability than Hungarian, which already solves the one-to-one case *exactly*. Only
  justified when the problem is too hard for exact methods — which the assignment problem isn't.
- **Generic MILP/LP solver for everything:** could express all of it, but it's a sledgehammer;
  Hungarian and min-cost flow are the specialised, faster, more explainable tools for these exact
  sub-problems.

### 5.6 The hybrid — why two-phase, and why it's a *composition* not a new algorithm
**What it proves:** that you can sometimes get the benefit of an expensive method by *stacking*
two cheap ones — and, just as importantly, **when you can't**. I chose the **two-phase
primary + fill** design: the primary solves everything, the secondary mops up the orders left
behind using whatever truck capacity remains.

**Why two-phase (and not priority-split or warm-start):** it's the most realistic — real dispatch
desks run a clean batch optimiser then a fast fallback for the stragglers — and it produces a
clean, defensible invariant: **Phase 2 can only add, so hybrid coverage ≥ primary coverage, always.**
That monotonicity is what makes the result easy to reason about and test.

**Why a composition, not a registry strategy:** it parameterises over *two* existing strategies,
so it lives at the engine level (`run_hybrid`) and reuses the same cost matrix, explanation, and
metrics machinery. Adding it as a "strategy" would have meant smuggling two sub-algorithm names
through the `solve(matrix)` signature — wrong shape.

**The honest result is the selling point.** In the one-to-one profiles (contested/scarce/tight)
the primary already uses every truck, so the hybrid is *identical* to the primary — combining
adds nothing, and the UI says so ("no gain here"). Only under **batching** (trucks with spare
capacity) does Phase 2 lift Hungarian's 8/12 to 11/12 (objective −14%). *Say this:* "The hybrid
shows judgement, not just plumbing — it adds value precisely when the fleet has slack to fill, and
I let the tool tell you honestly when it doesn't. When it does help, you've recovered much of
Min-Cost-Flow's consolidation win by composing two simple methods."

**Likely pushback — "Isn't the hybrid just a worse Min-Cost Flow?"** In the batching case they
reach the same coverage, yes. The point is different: the hybrid is a *general pattern* (any
optimiser + any fallback) that needs no new solver, and it's a faithful model of how layered
production systems actually run. Min-Cost Flow solves consolidation *natively and optimally*; the
hybrid *approximates* it by composition. Having both lets you compare the principled solver against
the pragmatic stack.

---

## 6. Metrics — why these, and the two non-obvious ones

Most metrics are standard (coverage, cost, on-time rate, lateness, fleet utilisation, load
balance, solve time). Two deserve a defence:

- **Optimality gap** — the headline. `(objective − hungarian_objective) / |hungarian_objective|`.
  It's the *one number* that answers the brief's question "how much did being greedy cost us?" A
  **negative** gap is meaningful, not a bug: it means an algorithm (min-cost flow) beat the
  *one-to-one* optimum by serving more orders via batching.
- **Priority-weighted fulfilment, reported separately** — see §4.4. The `scarce` profile is the
  case that proves why: greedy and Hungarian can have the *same* coverage but greedy spends 2×
  the cost — because it protects high-priority orders (slightly higher priority fulfilment) while
  Hungarian minimises total cost. The single "gap" number hides that trade; reporting priority on
  its own axis reveals it. *This is a great example to cite — it shows the metrics were designed,
  not just dumped.*

**Say this:** "The gap answers the brief directly; priority is a separate axis because collapsing
it into the objective would hide a real trade-off — the `scarce` profile shows exactly that."

---

## 7. Explainability — why runner-up + rejections + a note

**Decision:** Every assignment carries: the **cost breakdown** (distance/lateness/idle/priority),
the **runner-up truck** and its delta (the opportunity cost), the **rejected trucks with
reasons**, and an algorithm-specific **note**.

**Why:** The brief requires "some form of decision explanation." I went past a bare reason string
because the *interesting* explanation is the **counterfactual**: not just "T-07 got it" but "T-12
was the next best, +5.7 more" and "T-03 was rejected: missing refrigeration." The Hungarian
`note` is the money insight — it surfaces *when the global optimum deliberately assigned a
non-cheapest truck* so another order could be served far cheaper. That's the local-vs-global
trade made visible per-decision, which is the whole thesis of the project.

**Design choice:** explanations are built in the **base strategy**, not per algorithm. Each
algorithm only returns index pairs; the shared `allocate()` builds identical, equally-transparent
explanations for all. So adding an algorithm gives you explainability for free.

**Say this:** "The valuable explanation is the counterfactual — runner-up and rejection reasons —
and for Hungarian, *why* it picked a non-cheapest truck. That's local-vs-global, per decision."

---

## 8. Tech stack choices

| Choice | Why this | Why not the alternative |
|---|---|---|
| **FastAPI** | Async, Pydantic-native, free OpenAPI/`/docs`, minimal boilerplate | **Django** is heavyweight (ORM, admin, migrations) for a stateless compute API with no real DB |
| **Pydantic v2** | Validation + serialisation + OpenAPI schema from one model definition; algorithms operate on typed objects, never raw dicts | Hand-rolled dataclasses → manual validation, no free schema |
| **NumPy** | Dense cost matrix + vectorised feasibility/argmin; the natural substrate for all three solvers | Python lists → slower, clumsier matrix ops |
| **SciPy** | Compiled, correct Hungarian (`linear_sum_assignment`) | Hand-rolled Hungarian → error-prone, slower |
| **OR-Tools** | Compiled industrial min-cost-flow solver | NetworkX min_cost_flow → pure-Python, much slower |
| **React + Vite + TS** | Brief mandates React; Vite = instant dev + `/api` proxy (no CORS); TS mirrors the backend models for safety | CRA (deprecated/slow), plain JS (no model safety) |
| **Leaflet + CARTO/OSM** | Free, no API key, real lat/lon map — satisfies "no paid services" | Google/Mapbox → paid, keys, violate the brief |
| **Recharts** | Lightweight declarative charts for the metric bars | Heavier viz libs unjustified at this scale |
| **In-memory store behind a `Store` interface** | Single-user/local needs nothing more; interface makes SQLite/Postgres a drop-in | A real DB → setup cost and zero benefit for a local demo |

**Say this for the stack overall:** "Everything is free, local, and no-key per the brief; each
library is the specialised, compiled tool for its job, and the boundaries (Store interface,
strategy pattern) make the heavyweight versions drop-in later."

---

## 9. Architecture patterns — why they're there

- **Strategy pattern (the big one):** each algorithm is a subclass implementing only
  `solve(matrix) → pairs`. The base class handles explanation + unassigned-list construction. Net
  effect: **"compare N algorithms" is a one-line loop**, and adding an algorithm touches *one
  file* — the API, UI, metrics, and explanations all pick it up via the registry. This is the
  design choice that makes the whole comparison cheap and extensible.
- **`Store` interface / in-memory impl:** demonstrates the persistence seam without over-building.
  Swapping to a database changes one file, never the algorithms or handlers.
- **`engine.py` orchestration vs thin `main.py`:** routing stays separate from the
  build-matrix→solve→metrics pipeline. Keeps each layer single-responsibility and testable.
- **Stateless, deterministic compute:** scenario = f(profile, seed); allocation = f(scenario,
  algo, weights). Reproducible results, trivially parallelisable.

**Say this:** "The strategy pattern is the lever — it's why comparing three algorithms and adding
a fourth are both nearly free."

### 9.1 UI structure — why tabs, per-algorithm pages, and auto-run
**Decision:** A tabbed multi-page console — one focused page per algorithm, a *Compare All*
page, and a *Hybrid Lab* — over a shared sidebar that **auto-runs** the active tab on any change.

**Why per-algorithm pages first:** a single combined dashboard is great for *comparison* but poor
for *understanding* — you can't tell the story of one algorithm (what it is, what it optimises,
where it strands orders) when four are crammed together. A dedicated page gives each method room:
a hero that explains it in plain language, its own stat cards, and a full-size map you can read.
The Compare view is kept, but demoted to one tab — you teach with the single pages, then *prove*
the differences side-by-side.

**Why auto-run instead of a Run button:** the most convincing demo is *interaction* — drag the
lateness weight and watch routes re-colour, or flip the profile to Contested and watch coverage
drop. Forcing a button-press between every tweak kills that immediacy. (A Run button remains for an
explicit re-roll.) Scenario regeneration is keyed to its defining inputs (profile/counts/seed) and
re-allocation to the weights, so changing a slider doesn't pointlessly rebuild the scenario.

**Why single-algorithm pages still call `/allocate/compare` (against Hungarian):** that's how the
page gets a populated **optimality gap** for free — the gap is only meaningful relative to the
optimal baseline, so I run the chosen algorithm alongside Hungarian and read its result out.

**Say this:** "Single pages to *teach* each method, the Compare tab to *prove* the differences, the
Hybrid Lab to *explore* combinations, and the Simulator to see *all regimes at once* — and auto-run
so the whole thing feels like an instrument, not a form."

**The Simulator** answers "show me everything at once": pick several scenario profiles and each is
solved by all three algorithms, summarised on a card, and expandable into a full breakdown. It's the
one screen that makes the headline thesis visible — greedy's gap is small in *abundant*, grows in
*contested/tight*, and flips negative in *batching* — without manually flipping the profile dropdown.

---

## 10. Scenario generators — why deterministic profiles

**Decision:** Scenarios are generated deterministically from `(profile, n_trucks, n_orders,
seed)`. Five profiles: `abundant`, `contested`, `scarce`, `tight_windows`, `batching`.

**Why:** The profiles are **engineered to make the algorithm differences visible and
reproducible** — they're the experimental conditions. Each isolates one effect:
- `abundant` → loose resources → greedy ≈ optimal (small gap). *Proves greedy isn't always bad.*
- `contested` / `scarce` → contention → greedy strands orders, gap explodes. *Proves the global
  methods' value.*
- `tight_windows` → lateness dominates. *Proves the time-window modelling matters.*
- `batching` → `capacity_orders > 1` → min-cost flow beats one-to-one. *Proves the flow model.*

Determinism (seeding) means anyone re-running gets the exact numbers in the write-up — the
comparison is **reproducible**, not anecdotal.

**Say this:** "The profiles are experimental conditions, each isolating one effect, and seeding
makes every number in the write-up reproducible."

---

## 11. Testing — why these specific tests prove the point

The tests are chosen to validate *correctness of the comparison*, not just "code runs":
- **Hungarian vs brute-force** (small N): proves my "optimal" baseline is *actually* optimal.
  Everything hangs off this, so it's directly verified against exhaustive permutation search.
- **Min-cost-flow ≡ Hungarian at capacity 1**: proves the flow model agrees with the verified
  optimum where it should — independent corroboration.
- **Greedy never beats the optimal objective**: a sanity invariant — if greedy ever "won," the
  cost model or the gap math would be broken.
- **Property tests (Hypothesis)**: random scenarios always yield *valid* assignments (respecting
  capability/capacity) — guards against edge cases I didn't hand-pick.
- **Hybrid invariants** (parametrised over every profile × primary × secondary): the combined
  result stays valid; coverage is monotone (≥ primary); Phase 2 fills under batching; the hybrid
  equals the primary when there's no residual capacity. This is what lets me *claim* the
  monotonicity property rather than just assert it.
- **API integration**: the full request/response cycle, error codes, the compare endpoint fills
  the gap, the hybrid endpoint returns a phase-labelled combined result.

166 tests in total (the hybrid's full profile × primary × secondary sweep is most of the growth
from the original 87).

**Say this:** "The key test is Hungarian-vs-brute-force — it proves the baseline is truly optimal,
and the equivalence tests prove the others agree with it. The comparison rests on that."

---

## 12. Anticipated questions — fast answers

- **"Why not solve the real VRP?"** → NP-hard, no provable baseline for a gap, and it dissolves
  the greedy-vs-optimal comparison the brief asks for. Min-cost flow captures the realistic
  batching piece; full VRP is the named next step.
- **"Isn't haversine inaccurate?"** → For a *comparison* it doesn't matter — same distances for
  all algorithms. OSRM is the offline upgrade if true road distance is needed.
- **"Did you consider other algorithms / why not an auction?"** → I built a Bertsekas auction, then
  removed it: it only re-derived Hungarian's optimum by a different mechanism, and its one advantage
  (parallelism at scale) can't show in a serial Python benchmark. Cutting it kept the comparison
  sharp. Knowing what to leave out is part of the design. (See §5.4.)
- **"Does combining two algorithms help?"** → Only when the fleet has spare capacity. The
  two-phase hybrid (primary + fill) lifts Hungarian's 8/12 to 11/12 under *batching* (objective
  −14%), but is *identical* to the primary in one-to-one profiles where no truck is free. The
  honest "sometimes, and here's exactly when" is the point — and it recovers much of Min-Cost
  Flow's win by composition rather than a new solver.
- **"Why three algorithms instead of the two the brief required?"** → Each makes a *different*
  point: baseline (greedy), optimal (Hungarian), capacitated-generalisation (min-cost flow). Two
  would only show local-vs-global; the third adds the one-truck-many-orders dimension. (Plus the
  hybrid, which composes them.)
- **"Why is min-cost flow's gap negative — is that a bug?"** → No: it beats the *one-to-one*
  optimum by serving more orders via batching. Correct and expected.
- **"How would you productionise this?"** → Swap in OSRM for distance, persist behind the `Store`
  interface (SQLite/Postgres), move to real streaming dispatch windows, and add OR-Tools routing
  for multi-stop VRP. The seams for all four already exist.
- **"What's the single most important design decision?"** → The shared cost matrix. It's the
  experimental control that makes the comparison mean something.

---

## 12a. Two subtleties the build surfaced (great "I noticed…" answers)

These came out of tightening the geography, and they're the kind of thing that shows you actually
*understand* the model rather than just wiring solvers together.

- **Hungarian is *cost*-optimal, not *objective*-optimal.** My objective adds a flat 100-per-order
  penalty for non-coverage, but Hungarian minimises **cost** and serves as many as it can — it will
  serve an order that costs *more* than 100 to serve. So greedy, by happening to leave that order
  out, can post a *lower penalised objective* than the "optimal" method. I caught this when a test
  (`greedy ≥ hungarian objective`) failed, and rather than paper over it I corrected the test to the
  **true** invariant — *at equal coverage, Hungarian's cost ≤ greedy's* — and now state the nuance
  openly. *Say this:* "The optimality gap is defined against Hungarian's cost; on the coverage-
  penalised objective Hungarian isn't even optimal, and I can show exactly when greedy slips under it."
- **A weighting trap: the gap blows up when the optimal objective ≈ 0.** Moving to the (more compact)
  Kolkata geography shrank distances until the priority *bonus* nearly cancelled the distance cost —
  the optimal objective fell near zero and the gap *percentage* exploded (a +345% artifact). Fix:
  raise the default distance weight so distance stays dominant and the objective stays solidly
  positive. *Say this:* "Percentage gaps are unstable near a zero denominator — I rebalanced the
  weights so the objective is always meaningfully positive."

## 12b. Why Kolkata land hubs (the geography fix)

The first cut scattered points by random jitter around a single coastal centre — which dropped
trucks and orders into open water and piled markers on top of each other. I switched to placing
everything on a fixed list of **real land hubs across the Kolkata metro** with a small jitter:
guarantees land, spreads markers across recognisable towns, and still supports the profile knobs
(dispersed = draw from all hubs; clustered = draw from a few adjacent ones). *Say this:* "Synthetic
data should still be physically plausible and legible — hub-based placement gives both."

---

## 13. If you only remember five things

1. **One-cycle bipartite assignment** is the framing that makes "greedy vs optimal" a *valid*
   comparison with a *provable* baseline. (VRP would kill that.)
2. **Shared cost matrix** = the only variable is search quality. That's the scientific control.
3. **Hungarian is the anchor** — provably optimal, so it's what the gap is measured from; SciPy
   because it's compiled and correct.
4. **Min-cost flow is the domain insight** — batching is structurally impossible in one-to-one
   matching; capacity 1 recovers Hungarian, capacity >1 wins.
5. **The thesis:** the heuristic-vs-optimal gap is small when resources are loose and large when
   they're tight — so a better algorithm is worth most when the system is under stress.
