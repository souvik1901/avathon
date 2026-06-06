# Algorithm Comparison — Overview

A concise comparison of the allocation strategies: what each does, what it optimises, and
**when the difference between them actually matters**. Numbers come from
`benchmarks/run_benchmarks.py` (8 trucks × 12 orders, seed 7, unless noted).

> This is the high-level write-up. For the implementation deep-dive (annotated, line-by-line
> code walkthroughs of every algorithm), see **[`ALGORITHMS.md`](./ALGORITHMS.md)**.

---

## The common ground

Every algorithm consumes one cost matrix `C[truck][order]` built by `app/cost.py`:

- **Hard constraints** (capability, weight, volume, truck availability, shift window,
  finish-before-shift-end) gate feasibility. Infeasible pairs are `+∞` and can never be chosen.
- **Soft cost** for feasible pairs is
  `w_dist·road_km + w_late·lateness_min + w_idle·idle_slack − w_prio·priority`
  (priority enters as a *bonus* — a negative cost — so urgent orders are cheaper to serve).

The **objective** adds a uniform penalty for every unserved order:
`objective = Σ assigned cost + w_unassigned · n_unassigned`. The **optimality gap** is each
method's objective relative to Hungarian (the provable one-to-one optimum). *Same cost model
for all — so the only thing that differs between algorithms is how they search.*

---

## The strategies at a glance

| Algorithm | Optimality | Model | Complexity | One-line idea |
| --- | --- | --- | --- | --- |
| **Greedy** | Heuristic | 1 : 1 | `O(M·N)` | Take the cheapest free truck for each order, in priority order |
| **Hungarian** | **Optimal** | 1 : 1 | `O(n³)` | Solve the whole truck↔order matrix at once (Kuhn–Munkres) |
| **Min-Cost Flow** | Optimal (capacitated) | 1 : many | Polynomial | Model as a flow network so one truck can batch several orders |
| **Hybrid** | Composition | depends | primary + fill | Primary solves all; secondary fills the leftovers |

---

## Results by scenario

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
| **tight_windows** | greedy | 67% | 554.7 | 954.7 | **+18.8%** | 70% |
| (8 trucks, 12 orders) | hungarian | 67% | 403.7 | 803.7 | — | 64% |
| **batching** | greedy | 92% | 497.4 | 597.4 | **−22.0%** | 97% |
| (8 trucks ×3 cap, 12 orders) | hungarian | 67% | 365.5 | 765.5 | — | 77% |
| | min_cost_flow | 92% | 488.4 | 588.4 | **−23.1%** | 97% |

(`min_cost_flow == hungarian` exactly at `capacity_orders = 1`.)

---

## When each approach wins

- **Greedy** is near-optimal when resources are **abundant and dispersed** (+9.8% off optimal,
  though even here it stranded one order), and is the right call for **online/streaming** dispatch
  and at **extreme scale**. Where trucks are the bottleneck its penalty shows up as **extra cost at
  equal coverage** — +13.7% (*contested*) to +18.8% (*tight_windows*). *The tighter the problem,
  the more a global method is worth* (scarce +6% → contested +14% → tight +19%).
- **Hungarian** wins whenever the one-to-one problem is **contested or scarce** — provably
  optimal, and (via SciPy's compiled core) also the **fastest** method at every tested size.
- **Min-Cost Flow** wins the moment a truck can carry **more than one order** — in *batching* it
  covers 92% vs Hungarian's 67%, *beating* the one-to-one optimum (−23%). No 1:1 method can reach this.
- **Hybrid** adds coverage **only when the fleet has slack to fill** — under *batching*,
  `Hungarian → Greedy` lifts 8/12 to 11/12 (objective −14%); in one-to-one profiles it is
  identical to the primary.

**The subtle one — `scarce`:** greedy and Hungarian both cover 58%, yet greedy costs more
(310.6 vs 264.6). Greedy spends extra travel to protect *high-priority* orders (its
priority-fulfilment is actually higher, 51% vs 46%); Hungarian minimises total cost. The single gap
number hides that trade — which is why coverage, cost, and priority fulfilment are reported as
**separate** metrics.

---

## Solve time (median ms; contested, n/2 trucks; algorithm only)

```
algorithm          N=10    N=25    N=50   N=100   N=200   N=400
greedy             0.04    0.17    0.68    2.48    9.94   40.50
hungarian          0.01    0.02    0.07    0.24    1.22    6.89
min_cost_flow      0.10    0.49    1.68    6.25   24.03  131.04
```

SciPy's C-level Hungarian dominates at every tested size — it is both exact and fastest here.

---

## Summary

| If your situation is… | Use | Because |
| --- | --- | --- |
| Resources abundant, or online/streaming, or N huge | **Greedy** | Near-optimal when easy, fast, incremental |
| One-to-one, contested or scarce, exactness matters | **Hungarian** | Provably optimal *and* fastest at tested scale |
| A truck can serve multiple orders (consolidation) | **Min-Cost Flow** | Only method that covers more by batching |
| Optimal-first, then mop up leftover capacity | **Hybrid** | Composes two methods; helps when the fleet has slack |

**The headline:** the gap between a cheap heuristic and a global optimum is **small when
resources are loose and large when they're tight** — so a better algorithm is worth the most
exactly when the system is under stress.
