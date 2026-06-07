import type { CompareResult, Scenario, Assignment } from "../types";
import { ALGO_COLORS, ALGO_SHORT } from "../types";
import MapView from "./MapView";

interface Props {
  scenario: Scenario;
  compare: CompareResult;
  onPick: (algo: string, a: Assignment) => void;
}

export default function ComparisonGrid({ scenario, compare, onPick }: Props) {
  const keys = Object.keys(compare.results);
  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-head">
        <h3>Spatial comparison</h3>
        <span className="sub">routes = truck → pickup → dropoff · red = unassigned</span>
      </div>
      <div style={{ padding: 12 }}>
        <div className="grid-maps">
          {keys.map((k) => {
            const res = compare.results[k];
            const gap = res.metrics.optimality_gap;
            return (
              <div className="mini" key={k}>
                <div className="mini-head">
                  <span className="swatch" style={{ background: ALGO_COLORS[k] }} />
                  <span className="name">{ALGO_SHORT[k] ?? k}</span>
                  <span className="gap" style={{
                    color: (gap ?? 0) > 0 ? "var(--red)" : (gap ?? 0) < 0 ? "var(--green)" : "var(--text-dim)",
                  }}>
                    {res.metrics.assigned_count}/{res.metrics.total_orders} ·{" "}
                    {gap == null ? "base" : `${gap > 0 ? "+" : ""}${(gap * 100).toFixed(1)}%`}
                  </span>
                </div>
                <MapView
                  scenario={scenario}
                  assignments={res.assignments}
                  color={ALGO_COLORS[k]}
                  height={240}
                  showLegend={false}
                  interactive={false}
                  onPick={(a) => onPick(k, a)}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
