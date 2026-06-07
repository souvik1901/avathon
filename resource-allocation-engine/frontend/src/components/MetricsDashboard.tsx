import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { CompareResult } from "../types";
import { ALGO_COLORS, ALGO_SHORT } from "../types";

interface Props { compare: CompareResult; }

const fmtPct = (x?: number | null) =>
  x === null || x === undefined ? "—" : `${(x * 100).toFixed(1)}%`;

export default function MetricsDashboard({ compare }: Props) {
  const keys = Object.keys(compare.results);
  const rows = keys.map((k) => ({ key: k, ...compare.results[k].metrics }));

  // best/worst helpers per column (lower is better unless noted)
  const ext = (sel: (r: typeof rows[number]) => number, higherBetter = false) => {
    const vals = rows.map(sel);
    return { best: higherBetter ? Math.max(...vals) : Math.min(...vals),
             worst: higherBetter ? Math.min(...vals) : Math.max(...vals) };
  };
  const cls = (v: number, e: { best: number; worst: number }) =>
    v === e.best ? "best" : v === e.worst ? "worst" : "";

  const eObj = ext((r) => r.objective);
  const eCost = ext((r) => r.total_cost);
  const eCov = ext((r) => r.coverage, true);
  const eMs = ext((r) => r.solve_ms);

  const chartData = rows.map((r) => ({
    name: ALGO_SHORT[r.key] ?? r.key, key: r.key,
    objective: r.objective, coverage: +(r.coverage * 100).toFixed(1),
  }));

  // headline: greatest gap among non-baseline algorithms
  const gaps = rows.filter((r) => r.key !== "hungarian" && r.optimality_gap != null);
  const headline = gaps.sort(
    (a, b) => Math.abs((b.optimality_gap ?? 0)) - Math.abs((a.optimality_gap ?? 0)),
  )[0];

  return (
    <>
      <div className="callouts">
        <div className="callout" style={{ ["--c" as string]: "var(--amber)" }}>
          <div className="k">Optimal objective (Hungarian)</div>
          <div className="v">{compare.results["hungarian"]?.metrics.objective.toFixed(0) ?? "—"}</div>
        </div>
        {headline && (
          <div className="callout"
            style={{ ["--c" as string]: ALGO_COLORS[headline.key] }}>
            <div className="k">{ALGO_SHORT[headline.key]} vs optimal</div>
            <div className="v" style={{ color: (headline.optimality_gap ?? 0) > 0 ? "var(--red)" : "var(--green)" }}>
              {(headline.optimality_gap ?? 0) > 0 ? "+" : ""}
              {fmtPct(headline.optimality_gap)}
              <small> objective</small>
            </div>
          </div>
        )}
        <div className="callout" style={{ ["--c" as string]: "var(--cyan)" }}>
          <div className="k">Best coverage</div>
          <div className="v">{(eCov.best * 100).toFixed(0)}<small>%</small></div>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-head"><h3>Objective by algorithm</h3>
          <span className="sub">lower is better · includes unassigned penalty</span></div>
        <div style={{ padding: "12px 8px 4px" }}>
          <ResponsiveContainer width="100%" height={210}>
            <BarChart data={chartData} margin={{ top: 6, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid stroke="#232b36" vertical={false} />
              <XAxis dataKey="name" tick={{ fill: "#8b97a6", fontSize: 11, fontFamily: "JetBrains Mono" }} />
              <YAxis tick={{ fill: "#8b97a6", fontSize: 11, fontFamily: "JetBrains Mono" }} />
              <Tooltip
                contentStyle={{ background: "#11151b", border: "1px solid #33404f",
                  fontFamily: "JetBrains Mono", fontSize: 12 }}
                cursor={{ fill: "rgba(255,255,255,0.04)" }}
              />
              <Bar dataKey="objective" radius={[3, 3, 0, 0]}>
                {chartData.map((d) => <Cell key={d.key} fill={ALGO_COLORS[d.key]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head"><h3>Metric matrix</h3>
          <span className="sub">green = best · red = worst</span></div>
        <div style={{ overflowX: "auto" }}>
          <table className="metrics">
            <thead>
              <tr>
                <th>Algorithm</th><th>Cov</th><th>Cost</th><th>Objective</th>
                <th>Gap</th><th>On-time</th><th>Latē (m)</th><th>Util</th>
                <th>Load CV</th><th>Pri-fulfil</th><th>Solve (ms)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <td className="algo">
                    <span className="swatch" style={{ background: ALGO_COLORS[r.key] }} />
                    {ALGO_SHORT[r.key] ?? r.key}
                  </td>
                  <td className={cls(r.coverage, eCov)}>{(r.coverage * 100).toFixed(0)}%</td>
                  <td className={cls(r.total_cost, eCost)}>{r.total_cost.toFixed(1)}</td>
                  <td className={cls(r.objective, eObj)}>{r.objective.toFixed(1)}</td>
                  <td className={(r.optimality_gap ?? 0) > 0 ? "worst" : (r.optimality_gap ?? 0) < 0 ? "best" : ""}>
                    {r.optimality_gap == null ? "—"
                      : `${r.optimality_gap > 0 ? "+" : ""}${(r.optimality_gap * 100).toFixed(1)}%`}
                  </td>
                  <td>{(r.on_time_rate * 100).toFixed(0)}%</td>
                  <td>{r.avg_lateness_min.toFixed(1)}</td>
                  <td>{(r.fleet_utilisation * 100).toFixed(0)}%</td>
                  <td>{r.load_balance_cv.toFixed(2)}</td>
                  <td>{(r.priority_weighted_fulfilment * 100).toFixed(0)}%</td>
                  <td className={cls(r.solve_ms, eMs)}>{r.solve_ms.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
