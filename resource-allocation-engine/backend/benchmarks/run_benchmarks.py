"""
Benchmark harness.

Run from the backend directory:
    python -m benchmarks.run_benchmarks            # profile comparison + scaling
    python -m benchmarks.run_benchmarks --json out.json

Produces (a) a per-profile comparison of all four algorithms and (b) a scaling
study of solve time vs. instance size. This is the evidence behind the write-up.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time

from app.engine import run_algorithm, run_comparison
from app.generators import generate_scenario

ALGOS = ["greedy", "hungarian", "min_cost_flow"]
PROFILES = ["abundant", "contested", "scarce", "tight_windows", "batching"]


def profile_table(seed: int = 7) -> list[dict]:
    rows: list[dict] = []
    for profile in PROFILES:
        sc = generate_scenario(profile, n_trucks=8, n_orders=12, seed=seed)
        cmp = run_comparison(sc, ALGOS)
        for algo, res in cmp.results.items():
            m = res.metrics
            rows.append(dict(
                profile=profile, algorithm=algo, trucks=len(sc.trucks),
                orders=len(sc.orders), coverage=m.coverage, total_cost=m.total_cost,
                objective=m.objective, optimality_gap=m.optimality_gap,
                on_time_rate=m.on_time_rate, avg_lateness=m.avg_lateness_min,
                fleet_util=m.fleet_utilisation, load_cv=m.load_balance_cv,
                pri_fulfil=m.priority_weighted_fulfilment, solve_ms=m.solve_ms,
            ))
    return rows


def scaling_study(sizes=(10, 25, 50, 100, 200, 400), repeats: int = 3) -> list[dict]:
    """Time ONLY the algorithm's solve step (the cost matrix is built once and
    reused), so the numbers reflect algorithmic complexity rather than the shared
    O(N·M) matrix construction."""
    from app.cost import build_cost_matrix
    from app.models import CostConfig
    from app.strategies import get_strategy

    rows: list[dict] = []
    for n in sizes:
        for algo in ALGOS:
            strat = get_strategy(algo)
            times = []
            for r in range(repeats):
                sc = generate_scenario("contested", n_trucks=max(2, n // 2),
                                        n_orders=n, seed=100 + r)
                cm = build_cost_matrix(sc.trucks, sc.orders,
                                       sc.decision_time, CostConfig())
                t0 = time.perf_counter()
                strat.solve(cm)
                times.append((time.perf_counter() - t0) * 1000.0)
            rows.append(dict(n_orders=n, algorithm=algo,
                             median_ms=round(statistics.median(times), 3),
                             min_ms=round(min(times), 3)))
    return rows


def _print_profile_table(rows: list[dict]) -> None:
    hdr = (f"{'profile':14s} {'algorithm':14s} {'cov':>5s} {'cost':>9s} "
           f"{'objective':>10s} {'gap':>8s} {'ontime':>7s} {'util':>6s} "
           f"{'pri':>5s} {'ms':>7s}")
    print("\n=== PROFILE COMPARISON (8 trucks x 12 orders, seed 7) ===")
    print(hdr)
    print("-" * len(hdr))
    last = None
    for r in rows:
        if last and last != r["profile"]:
            print()
        print(f"{r['profile']:14s} {r['algorithm']:14s} {r['coverage']:5.2f} "
              f"{r['total_cost']:9.1f} {r['objective']:10.1f} "
              f"{str(r['optimality_gap']):>8s} {r['on_time_rate']:7.2f} "
              f"{r['fleet_util']:6.2f} {r['pri_fulfil']:5.2f} {r['solve_ms']:7.2f}")
        last = r["profile"]


def _print_scaling(rows: list[dict]) -> None:
    print("\n=== SCALING STUDY (solve time, median ms; contested, n/2 trucks) ===")
    sizes = sorted({r["n_orders"] for r in rows})
    print(f"{'algorithm':14s} " + " ".join(f"{n:>9d}" for n in sizes))
    print("-" * (14 + 10 * len(sizes)))
    for algo in ALGOS:
        cells = []
        for n in sizes:
            ms = next(r["median_ms"] for r in rows
                      if r["n_orders"] == n and r["algorithm"] == algo)
            cells.append(f"{ms:9.2f}")
        print(f"{algo:14s} " + " ".join(cells))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=str, default=None, help="write raw results to JSON")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    profile_rows = profile_table(args.seed)
    scaling_rows = scaling_study()

    _print_profile_table(profile_rows)
    _print_scaling(scaling_rows)

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"profiles": profile_rows, "scaling": scaling_rows}, f, indent=2)
        print(f"\nWrote {args.json}")


if __name__ == "__main__":
    main()
