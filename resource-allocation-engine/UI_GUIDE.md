# UI Guide & Demo Walkthrough

A practical guide to the Dispatch Engine console: what every part of the screen means, how to
read it, and a ready-to-present **demo script** you can follow (or hand to someone) start to
finish. No prior context needed.

> Open the app at **http://localhost:5173** (backend must be running on `:8000`). It loads on
> the **Greedy** tab with a default *Contested* scenario already solved.

---

## 1. The mental model (read this first)

The whole app does one thing, over and over:

> **Take a set of trucks and a set of delivery orders, and decide which truck does which order — cheaply.**

- A **truck** = a resource: it has a location, capacity (weight/volume), capabilities
  (refrigerated/hazmat/liftgate), a work shift, and possibly room for several orders.
- An **order** = a request: a pickup, a dropoff, a weight/volume, a deadline (`due_by`), a
  priority (1–5), and maybe a required capability.
- An **assignment** = one truck doing one order. Its **route** on the map is
  `truck → pickup → dropoff`.

Every method you'll see is solving that same problem on the same data; they differ only in *how
cleverly* they search. The app exists to **show those differences**.

**Two ideas to keep saying out loud during a demo:**
1. **"Same cost model, different search."** Every algorithm scores truck–order pairs identically;
   the only thing that varies is the search. That's why the comparison is fair.
2. **"The optimality gap is the headline."** It's one number: *how much worse than the optimal
   plan is this?* `+20%` = this method's plan costs 20% more than the best possible.

---

## 2. Screen layout

```
┌─────────────────────────────────────────────────────────────────────┐
│ TOP BAR   Dispatch.Engine            status: ready / solving / error  │
├─────────────────────────────────────────────────────────────────────┤
│ TABS  Greedy │ Hungarian │ Min-Cost Flow │ Compare │ Hybrid │ Simulator│
├──────────────┬──────────────────────────────────────────────────────┤
│  SIDEBAR     │  MAIN AREA (changes per tab)                          │
│  (shared)    │                                                       │
│  • Scenario  │   hero / stat cards / maps / tables                   │
│  • Weights   │                                                       │
│  • Run       │                                                       │
└──────────────┴──────────────────────────────────────────────────────┘
```

- **Top bar** — branding + a status light: green = ready, amber pulse = solving, red = error.
- **Tabs** — switch what the main area shows. The accent colour of the whole UI follows the tab.
- **Sidebar (left, always there)** — controls the scenario and cost weights. **Changing anything
  here re-runs the current tab automatically** — you rarely need the Run button.
- **Main area** — the content for the active tab.

---

## 3. The sidebar controls (what each does)

**Scenario**
- **Profile** — the *shape* of the problem. This is your most powerful demo lever:
  | Profile | What it sets up | What it reveals |
  |---|---|---|
  | **Contested** | many orders clustered near a few trucks | greedy strands orders; global methods win |
  | **Abundant** | far more trucks than orders, spread out | everything does well; greedy ≈ optimal |
  | **Scarce** | fewer trucks than orders | not everything *can* be served; priorities matter |
  | **Tight windows** | very short deadlines | lateness dominates; coverage drops |
  | **Batching** | trucks can carry several orders | Min-Cost Flow & the hybrid shine |
  Selecting a profile shows a short **description box** under the dropdown explaining what it sets up.
  (All scenarios are placed on real **Kolkata-metro** land hubs, so points spread across towns and
  stay off the water.)
- **Trucks / Orders** — how many of each.
- **Seed** — the random seed. **Same seed = exact same scenario every time** (reproducible).

**Cost weights** — six sliders, each with a one-line description beneath it:
- **Distance** — cost per km travelled (× the truck's cost/km). Higher → prefer nearer trucks.
- **Lateness** — cost per minute past a deadline. Higher → protect SLAs even at extra travel.
- **Idle / underuse** — penalty for a big truck on a tiny order (wasted capacity).
- **Priority bonus** — makes urgent orders cheaper to serve, biasing the search toward them.
- **Unassigned penalty** — flat cost for every order left unserved. Higher → push coverage up.
- **Road circuity** — straight-line km × this ≈ road km (1.3 ≈ a typical detour).
- Drag any slider and watch the maps/metrics update live. *Great demo move: crank **Lateness** up and
  watch routes change to protect deadlines, or drop **Unassigned penalty** to let a method abandon
  expensive orders.*

**Run** — forces a fresh solve (you mostly won't need it; the app auto-runs on change).

---

## 4. Reading the map (every tab has one)

Markers are **icons**, not dots, and each shape means something different:

| On the map | Means |
|---|---|
| 🚚 **Truck icon** (rounded square) | a truck at its location. **Bright/glowing = working** (it got an order this cycle); **dim/grey = idle** (unused). |
| 📦 **Package icon** (matches the tab colour) | an order's **pickup** that **got assigned**. Bigger box = higher priority. |
| 📦 **Red dashed package** (pulsing) | an order left **unassigned**. |
| 📍 **Pin** | an assigned order's **dropoff** (where the route ends). |
| **Dashed faint line** | the **empty "deadhead" leg** — the truck driving to the pickup with no load. |
| **Solid bright line** | the **loaded leg** — pickup → dropoff carrying the order. |
| **Hover any icon/line** | a styled snippet pops up: truck → capacity, batch size, speed, capabilities, shift; pickup → demand, required capability, due-by, who serves it; line → cost, km, ETA, lateness. |
| **Click a line** | opens the **explanation drawer** (see §6). |

Quick read: **lots of bright trucks + coloured packages + few red ones = good coverage.** A faint
dashed line that's *long* means an expensive empty drive to reach the pickup. Many red pulsing
packages = orders nobody could serve.

---

## 5. The tabs, one by one

### Greedy / Hungarian / Min-Cost Flow (the first three)
Each is a **dedicated page for one algorithm**:
- **Hero header** — plain-language description + four facts: *optimality, model, complexity,
  best-when*. (This is your script — just read it.)
- **Stat cards** — six headline numbers; **hover the small ⓘ on any card** for a full explanation:
  - **Coverage** — % of orders served (and the count).
  - **Objective** — total plan cost incl. a penalty for unserved orders. *Lower is better.* Shows
    the **gap vs optimal** underneath.
  - **On-time rate** — % of served orders that beat their deadline.
  - **Fleet used** — % of trucks put to work.
  - **Priority served** — % of *priority weight* served (did the important ones get done?).
  - **Solve time** — how long the algorithm took (ms).
- **Map** — that algorithm's routes (click any for the explanation).
- **Decision detail panel** (right) — now a full breakdown: the **objective build-up**
  (total cost + unassigned penalty = objective), **cost-composition bars** showing how the whole
  plan's cost splits across distance / lateness / idle / priority, a **click-through assignment
  list** (every truck→order with km, lateness and cost — click a row to open its explanation), and
  the **unassigned** orders.

### Compare All (tab 4)
Everything side by side — this is where you *prove* the differences:
- **Callouts** — optimal objective, the biggest gap, best coverage.
- **Objective bar chart** — taller = worse plan. The shortest bar is the best method.
- **Metric matrix** — every metric for every algorithm; **green = best, red = worst** in each
  column. The single most information-dense view.
- **Mini-maps** — one per algorithm, to eyeball the spatial differences.
- **Focus map** — a big map; click the algorithm buttons to switch which one it shows.
- Use the sidebar's **Algorithms** chips (this tab only) to choose which methods to include.

### Hybrid Lab (tab 5)
Tests **combining two methods**: *primary solves everything, secondary fills the leftovers.*
- **Two pickers** — choose the **Phase 1 (primary)** and **Phase 2 (fill)** strategies.
- **Verdict banner** — plain-language: did combining help, and why / why not.
- **Combined vs each alone** table — coverage, objective, solve time for the hybrid and each
  component on its own.
- **Stat cards + map** — for the combined result. Click a route — the explanation tells you
  *which phase* placed that order.

### Simulator (tab 6)
Run **several scenarios at once** and compare regimes side by side.
- **Scenario chips** — toggle which profiles to simulate (contested, abundant, scarce,
  tight windows, batching). The sidebar's truck/order/seed/weights apply to all of them.
- **Summary cards** — one per selected profile: best coverage, the optimal (Hungarian) objective,
  greedy's gap, and a little bar per algorithm (taller = worse objective).
- **Click a card** → a full breakdown opens below: the metric matrix, the side-by-side maps, and a
  short note on **what's happening and why** in that scenario. Great for showing, in one screen,
  that greedy is fine in *abundant* but loses ground in *tight windows*, and that *batching* is
  where Min-Cost Flow pulls ahead.

---

## 6. The explanation drawer (click any route)

This is the "why" behind a single decision. It shows:
- **Total cost / travel / ETA / predicted lateness** for that assignment.
- **Cost breakdown** — how distance, lateness, idle, and priority added up (with bars).
- **Counterfactual** — the **next-best truck** and how much more it would have cost (the
  "opportunity cost"). This is the gold: it shows the decision wasn't arbitrary.
- **A note** — e.g. for Hungarian, *"assigned a non-cheapest truck here so another order could be
  served far more cheaply"* — the global-vs-local trade in one sentence. For the hybrid, *which
  phase* placed it.
- **Rejected trucks** — which trucks were ruled out and the hard reason (e.g. "missing capability:
  refrigerated", "cannot finish before shift end").

---

## 7. A 5-minute demo script (say this, click that)

**Setup:** start on the **Hungarian** tab, profile **Contested**, 8 trucks / 12 orders, seed 7.

1. **Frame it (30s).** *"This assigns delivery trucks to orders. Every algorithm uses the same
   cost model — distance, lateness, wasted capacity, priority — so the only difference is how
   smartly each one searches. I'll show four, then compare them, then combine them."*

2. **Hungarian — the gold standard (45s).** *"Hungarian finds the provably cheapest one-truck-one-
   order plan. It's my baseline."* Point at **Coverage** and **Objective**. *"6 of 12 served here
   — contested means lots of orders chasing few trucks."* Click a route → drawer. *"Every decision
   is explained: the chosen truck, the runner-up, and why others were rejected."*

3. **Greedy — the cheap heuristic (45s).** Click the **Greedy** tab. *"Greedy just grabs the
   cheapest truck for each order in turn — fast, but short-sighted."* Point at **Objective** and
   its **gap**: *"+20% worse than optimal, and it serves fewer orders — an early greedy pick
   stranded a later one. That's the whole story: greedy is fine when it's easy, costly under
   pressure."*

4. **Prove it side by side (45s).** Click **Compare All**. *"Same scenario, all methods."* Point at
   the **objective bar chart** (greedy's bar is tallest) and the **metric matrix** (green = best).
   *"Hungarian and Min-Cost Flow tie at the optimum; greedy is the outlier."*

5. **When does greedy stop mattering? (30s).** In the sidebar switch profile to **Abundant**.
   *"Loosen the constraints — now everyone's near-optimal. The gap only matters when resources are
   tight."* (This is the key insight of the whole project.)

6. **Min-Cost Flow — the realistic twist (40s).** Switch profile to **Batching**, open the
   **Min-Cost Flow** tab. *"Real trucks carry several orders. Only this method models that —
   watch coverage jump because one truck batches nearby orders. It actually beats the one-to-one
   optimum here."*

7. **Hybrid Lab — combining methods (60s).** Open **Hybrid Lab**; set **Phase 1 (primary) =
   Hungarian**, **Phase 2 (fill) = Greedy**. *"Primary solves everything; the fill phase mops up the
   orders it left, using leftover truck capacity."* Show the contrast by flipping the sidebar profile:
   - **① Batching → it helps.** Profile → **Batching**. Green **verdict**, and the *combined‑vs‑alone*
     table reads: *"Hungarian alone 8/12 (obj 765); the fill phase adds **3** orders → hybrid **11/12
     (92%)**, objective **658** — about −14% over Hungarian alone."* Click a new route → its note says
     *"Phase 2 — filled by greedy."*
   - **② Contested → no gain.** Profile → **Contested**. Amber **verdict**: *"phase‑2 fills = **0**,
     the hybrid is identical to Hungarian (8/12, obj 733). With 8 trucks all used there's no spare
     capacity to fill — and the tool says so honestly."*
   - *(If asked why greedy‑alone (597) is cheaper than the hybrid (658) in batching: greedy is already
     capacity‑aware and Min‑Cost Flow is optimal‑capacitated — the hybrid only **rescues the primary**,
     it doesn't beat a purpose‑built capacity method. That's the honest framing.)*

8. **Simulator — all regimes at once (30s).** Open the **Simulator**, select **Contested +
   Abundant + Batching**. *"One screen, three regimes."* Point at the cards: *"Greedy's gap is small
   in abundant, bigger in contested, and flips negative in batching where consolidation wins."*
   Click the **Batching** card to drop into its full breakdown.

9. **Close (15s).** *"One cost model, three searches, a hybrid, and a simulator — a clear, measured
   answer to 'which method, when?'"*

---

## 8. Cheat-sheet — what "good" looks like

- **High coverage + low objective + low gap** = a good plan.
- **Gap = 0** → this method matched the optimum (Hungarian is always 0; it's the baseline).
- **Negative gap** → it *beat* one-to-one Hungarian (Min-Cost Flow / hybrid under batching).
- **High coverage but high cost** (e.g. greedy in *scarce*) → it served the important orders but
  spent more doing it — check **Priority served** to see the trade.

## 9. If something looks wrong

- **Red status light / error banner** → the backend isn't reachable. Confirm `uvicorn` is running
  on `:8000` (`curl http://localhost:8000/` should answer).
- **Everything red/unassigned** → likely *Scarce* or *Tight windows* with extreme weights; reset
  weights or pick *Abundant*.
- **Map empty** → give it a second after changing inputs (the amber light means it's solving), or
  hit **Run**.

---

## 10. Scenario profiles in depth

The five profiles are **engineered experiments** — each isolates one condition so a particular
algorithm difference becomes visible. They all place trucks and orders on real Kolkata-metro land
hubs; what changes is *how many* trucks, *where the orders cluster*, *how tight the deadlines are*,
and *whether a truck can carry several orders*. Numbers below are the defaults (8 trucks × 12
orders, seed 7); the profile may override the truck count as noted.

### Contested  *(the default)*
- **Sets up:** orders concentrated on **two** adjacent hubs while the 8 trucks are spread across the
  whole metro; one truck = one order. Loose-ish deadlines.
- **What happens:** only a few trucks are near the demand, and with 8 trucks for 12 orders, **all
  methods cap at 8/12 = 67% coverage** (the fleet runs out of trucks). The difference is **cost**:
  greedy's myopic early picks force costlier later assignments.
- **Numbers:** coverage 67% for all; objective — greedy **833 (+13.7%)** vs Hungarian/MCF **733**.
- **Watch:** the **Objective** card and its gap, *not* coverage. This is the "equal coverage,
  different cost" case.

### Abundant
- **Sets up:** trucks **far outnumber** orders (~20 trucks for 12), dispersed across all hubs; loose
  deadlines. one truck = one order.
- **What happens:** almost every order has a cheap nearby idle truck, so local choices rarely
  collide → greedy is **near-optimal**. Hungarian/MCF hit full coverage; greedy occasionally
  strands one order.
- **Numbers:** Hungarian/MCF **100% · obj 376**; greedy **92% · obj 413 (+9.8%)**.
- **Watch:** the small gap — proof that *when resources are loose, the cheap heuristic is fine*.

### Scarce  *(the subtle one)*
- **Sets up:** **fewer trucks than orders** (~7 for 12), dispersed; one truck = one order.
- **What happens:** not everything *can* be served (coverage capped ~58% for all). Greedy and
  Hungarian tie on coverage, **but greedy spends more** — because it burns extra travel to protect
  **high-priority** orders, while Hungarian minimises total cost.
- **Numbers:** all **58% (7/12)**; greedy **obj 810 (+6.0%)**, priority-served **51%**;
  Hungarian/MCF **obj 765**, priority-served **46%**.
- **Watch:** compare the **Priority served** card against the cost gap — greedy is "worse" on cost
  yet *better* on priority. This is why coverage, cost, and priority are reported **separately**.

### Tight windows
- **Sets up:** same fleet as contested, but **very short deadlines** (due-by 60–110 min). one
  truck = one order.
- **What happens:** distant trucks can't arrive in time, so feasibility and **lateness** dominate.
  Greedy's poor routing now also breaks deadlines → its **largest cost gap**.
- **Numbers:** all **67%**; greedy **obj 955 (+18.8%)**; Hungarian/MCF **obj 804** (and a lower
  on-time rate shows the SLA pressure).
- **Watch:** the **On-time rate** and **avg/max lateness** cards, plus the biggest objective gap.

### Batching  *(the only coverage-diverging one)*
- **Sets up:** orders cluster on a few adjacent hubs **and each truck can carry up to 3 orders**
  (`capacity_orders = 3`). 8 trucks.
- **What happens:** one-to-one **Hungarian is capped at 8/12 = 67%** (one order per truck), but
  **Min-Cost Flow consolidates** several nearby orders onto one truck and reaches **92%** — *beating*
  the one-to-one optimum. Capacity-aware greedy also reaches 92%.
- **Numbers:** Hungarian **67% · obj 765**; Min-Cost Flow **92% · obj 588 (−23%)**; greedy
  **92% · obj 597 (−22%)**. (Negative gap = beat one-to-one Hungarian.)
- **Watch:** this is the one profile where **coverage itself diverges** — the case that justifies
  Min-Cost Flow and the Hybrid Lab's fill phase.

> **The throughline:** the gap between a cheap heuristic and the optimum is **small when resources
> are loose (abundant) and large when they're tight (contested/tight)** — and the one-to-one model's
> ceiling only breaks when a truck can carry several orders (batching). Full numbers and the
> code-level reasoning are in [`ALGORITHMS.md`](./ALGORITHMS.md); the concise version is in
> [`ALGORITHMS_OVERVIEW.md`](./ALGORITHMS_OVERVIEW.md).
