import type { ReactNode } from "react";
import type { Metrics } from "../types";

interface Props { m: Metrics; accent: string; }

/** Headline stat cards for a single allocation result. Each card carries an
 *  `info` description revealed on hover (the ⓘ badge). */
export default function AlgoStats({ m, accent }: Props) {
  const cards: { k: string; v: ReactNode; sub?: string; c: string; info: string }[] = [
    {
      k: "Coverage", c: accent,
      v: <>{(m.coverage * 100).toFixed(0)}<small>%</small></>,
      sub: `${m.assigned_count} / ${m.total_orders} orders`,
      info: "Share of orders that got a truck. The first thing to look at: an algorithm that leaves orders unserved is failing the core job, whatever its cost.",
    },
    {
      k: "Objective", c: "var(--amber)",
      v: m.objective.toFixed(0),
      sub: m.optimality_gap == null ? "lower is better"
        : `${m.optimality_gap > 0 ? "+" : ""}${(m.optimality_gap * 100).toFixed(1)}% vs optimal`,
      info: "The single number being minimised: total assignment cost + a flat penalty (w_unassigned) for every unserved order. The % is the optimality gap vs Hungarian — how much worse than the provably-best plan this is. Negative = it beat one-to-one Hungarian (e.g. by batching).",
    },
    {
      k: "On-time rate", c: "var(--green)",
      v: <>{(m.on_time_rate * 100).toFixed(0)}<small>%</small></>,
      sub: `avg late ${m.avg_lateness_min.toFixed(1)} min`,
      info: "Share of served orders that arrive by their due-by deadline. Pairs with avg/max lateness to show SLA health — a high coverage with low on-time means orders are served but late.",
    },
    {
      k: "Fleet used", c: "var(--cyan)",
      v: <>{(m.fleet_utilisation * 100).toFixed(0)}<small>%</small></>,
      sub: `load CV ${m.load_balance_cv.toFixed(2)}`,
      info: "Distinct trucks used ÷ trucks available. Load CV is the spread of orders-per-truck (0 = perfectly even). Low fleet use can mean spare capacity — exactly what the Hybrid Lab's fill phase exploits.",
    },
    {
      k: "Priority served", c: "var(--violet)",
      v: <>{(m.priority_weighted_fulfilment * 100).toFixed(0)}<small>%</small></>,
      sub: "weighted by priority",
      info: "Served priority mass ÷ total priority mass. Reported separately from cost because priority is a competing goal: two methods with equal coverage can differ on whether they served the orders that mattered.",
    },
    {
      k: "Solve time", c: "var(--blue)",
      v: <>{m.solve_ms.toFixed(2)}<small> ms</small></>,
      sub: `${m.total_travel_km.toFixed(0)} km total`,
      info: "Wall-clock time for the algorithm's search only (matrix build excluded). The price of optimality — Hungarian is exact and, via SciPy's compiled core, also the fastest here; greedy is simple but scans every truck per order; min-cost-flow does the most work.",
    },
  ];
  return (
    <div className="stats">
      {cards.map((c) => (
        <div className="stat" key={c.k} style={{ ["--stat-c" as string]: c.c }}>
          <div className="s-k">
            {c.k}
            <span className="s-info" tabIndex={0}>ⓘ<span className="s-pop">{c.info}</span></span>
          </div>
          <div className="s-v">{c.v}</div>
          {c.sub && <div className="s-sub">{c.sub}</div>}
        </div>
      ))}
    </div>
  );
}
