import type { Assignment, CompareResult, Scenario } from "../types";
import { ALGO_COLORS, ALGO_SHORT } from "../types";
import MetricsDashboard from "./MetricsDashboard";
import ComparisonGrid from "./ComparisonGrid";
import MapView from "./MapView";

interface Props {
  scenario: Scenario | null;
  compare: CompareResult | null;
  focus: string; setFocus: (k: string) => void;
  busy: boolean;
  onPick: (algo: string, a: Assignment) => void;
}

export default function ComparePage(p: Props) {
  if (!p.scenario || !p.compare) {
    return (
      <div className="page">
        <div className="skeleton" style={{ height: 120, marginBottom: 16 }} />
        <div className="skeleton" style={{ height: 360 }} />
      </div>
    );
  }

  const focusResult = p.compare.results[p.focus];
  const keys = Object.keys(p.compare.results);

  return (
    <div className="page">
      <MetricsDashboard compare={p.compare} />
      <ComparisonGrid scenario={p.scenario} compare={p.compare}
        onPick={(algo, a) => p.onPick(algo, a)} />

      {focusResult && (
        <div className="panel">
          <div className="panel-head">
            <h3>Focus map</h3>
            <span className="sub">click any route for the decision explanation</span>
            <span className="spacer" />
            <div className="seg" style={{ ["--seg-c" as string]: ALGO_COLORS[p.focus] }}>
              {keys.map((k) => (
                <button key={k} className={p.focus === k ? "on" : ""}
                  style={p.focus === k ? { ["--seg-c" as string]: ALGO_COLORS[k] } : undefined}
                  onClick={() => p.setFocus(k)}>
                  {ALGO_SHORT[k] ?? k}
                </button>
              ))}
            </div>
          </div>
          <div style={{ padding: 12 }}>
            <MapView scenario={p.scenario} assignments={focusResult.assignments}
              color={ALGO_COLORS[p.focus]} height={560}
              onPick={(a) => p.onPick(p.focus, a)} />
          </div>
        </div>
      )}
    </div>
  );
}
