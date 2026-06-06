import { useEffect, useMemo, useState } from "react";
import type { AlgorithmInfo, AllocationResult, Assignment, CostConfig, Scenario } from "../types";
import { ALGO_BLURB, ALGO_COLORS, ALGO_SHORT, ALGO_TAGLINE } from "../types";
import MapView from "./MapView";
import AlgoStats from "./AlgoStats";

interface Props {
  algoKey: string;
  info?: AlgorithmInfo;
  scenario: Scenario | null;
  weights: CostConfig;
  result: AllocationResult | null;
  busy: boolean;
  onPick: (a: Assignment) => void;
}

const GLYPH: Record<string, string> = {
  greedy: "G", hungarian: "H", min_cost_flow: "F",
};

const COMP: [string, keyof Assignment["explanation"]["breakdown"], string][] = [
  ["distance", "distance", "var(--amber)"],
  ["lateness", "lateness", "var(--red)"],
  ["idle", "idle", "var(--cyan)"],
  ["priority bonus", "priority", "var(--green)"],
];

export default function AlgorithmPage(p: Props) {
  const accent = ALGO_COLORS[p.algoKey];
  const [shown, setShown] = useState<AllocationResult | null>(p.result);
  useEffect(() => { if (p.result) setShown(p.result); }, [p.result]);

  const m = shown?.metrics;

  // aggregate the per-assignment cost breakdown across the whole plan
  const agg = useMemo(() => {
    const s = { distance: 0, lateness: 0, idle: 0, priority: 0 };
    for (const a of shown?.assignments ?? []) {
      s.distance += a.explanation.breakdown.distance;
      s.lateness += a.explanation.breakdown.lateness;
      s.idle += a.explanation.breakdown.idle;
      s.priority += a.explanation.breakdown.priority;
    }
    return s;
  }, [shown]);
  const compMax = Math.max(1, Math.abs(agg.distance), Math.abs(agg.lateness), Math.abs(agg.idle), Math.abs(agg.priority));

  // assignment rows sorted by cost (most expensive decisions first)
  const rows = useMemo(
    () => [...(shown?.assignments ?? [])].sort((a, b) => b.cost - a.cost),
    [shown],
  );

  return (
    <div className="page" style={{ ["--accent" as string]: accent }}>
      <div className="hero">
        <div className="glyph">{GLYPH[p.algoKey] ?? "•"}</div>
        <div className="h-body">
          <h2>{p.info?.name ?? ALGO_SHORT[p.algoKey]}</h2>
          <div className="h-tag">{ALGO_TAGLINE[p.algoKey]}</div>
          <div className="h-blurb">{ALGO_BLURB[p.algoKey]}</div>
          {p.info && (
            <div className="h-pills">
              <span className="pill">optimality <b>{p.info.optimality}</b></span>
              <span className="pill">model <b>{p.info.model}</b></span>
              <span className="pill">complexity <b>{p.info.complexity}</b></span>
              <span className="pill">best when <b>{p.info.best_when}</b></span>
            </div>
          )}
        </div>
      </div>

      {m && <AlgoStats m={m} accent={accent} />}

      <div className="algo-grid">
        <div className="panel">
          <div className="panel-head">
            <span className="swatch" style={{ width: 11, height: 11, borderRadius: 3, background: accent, boxShadow: `0 0 8px ${accent}` }} />
            <h3>{ALGO_SHORT[p.algoKey]} routes</h3>
            <span className="sub">truck → pickup → dropoff · click a route to explain · red = unassigned</span>
            {p.busy && <><span className="spacer" /><span className="spinner" /></>}
          </div>
          <div style={{ padding: 12 }}>
            {p.scenario && shown ? (
              <MapView scenario={p.scenario} assignments={shown.assignments}
                color={accent} height={600} onPick={p.onPick} />
            ) : (
              <div className="skeleton" style={{ height: 600 }} />
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-head"><h3>Decision detail</h3>
            {m && <span className="sub">{m.assigned_count}/{m.total_orders} served</span>}</div>
          <div className="dd-body">
            {m ? (
              <>
                <div className="kv"><span className="k">Total cost</span><span className="mono">{m.total_cost.toFixed(1)}</span></div>
                <div className="kv"><span className="k">+ unassigned penalty</span><span className="mono">{(m.objective - m.total_cost).toFixed(1)}</span></div>
                <div className="kv"><span className="k">= objective</span><span className="mono" style={{ color: accent }}>{m.objective.toFixed(1)}</span></div>
                <div className="kv"><span className="k">Optimality gap</span>
                  <span className="mono" style={{ color: (m.optimality_gap ?? 0) > 0 ? "var(--red)" : (m.optimality_gap ?? 0) < 0 ? "var(--green)" : "var(--text-dim)" }}>
                    {m.optimality_gap == null ? "—" : `${m.optimality_gap > 0 ? "+" : ""}${(m.optimality_gap * 100).toFixed(1)}%`}
                  </span></div>
                <div className="kv"><span className="k">Avg / max lateness</span><span className="mono">{m.avg_lateness_min.toFixed(1)} / {m.max_lateness_min.toFixed(1)} m</span></div>
                <div className="kv"><span className="k">Travel · avg/order</span><span className="mono">{m.total_travel_km.toFixed(0)} · {m.avg_travel_km.toFixed(1)} km</span></div>

                <div className="dd-section">cost composition (whole plan)</div>
                {COMP.map(([lbl, key, color]) => {
                  const v = agg[key];
                  return (
                    <div key={key} className="comp-row">
                      <div className="comp-top"><span>{lbl}</span><span className="mono">{v.toFixed(1)}</span></div>
                      <div className="bar"><span style={{ width: `${(Math.abs(v) / compMax) * 100}%`, background: color }} /></div>
                    </div>
                  );
                })}

                <div className="dd-section">assignments · click to explain</div>
                <div className="dd-list">
                  {rows.map((a) => (
                    <button key={`${a.truck_id}-${a.order_id}`} className="dd-row" onClick={() => p.onPick(a)}>
                      <span className="mono ddr-id">{a.truck_id}→{a.order_id}</span>
                      <span className="mono ddr-km">{a.travel_km.toFixed(0)}km</span>
                      {a.predicted_lateness_min > 0
                        ? <span className="mono ddr-late">+{a.predicted_lateness_min.toFixed(0)}m</span>
                        : <span className="mono ddr-ok">on-time</span>}
                      <span className="mono ddr-cost">{a.cost.toFixed(1)}</span>
                    </button>
                  ))}
                </div>

                {shown && shown.unassigned_order_ids.length > 0 && (
                  <>
                    <div className="dd-section red">unassigned ({shown.unassigned_order_ids.length})</div>
                    <div className="mono" style={{ fontSize: 11, color: "var(--red)", lineHeight: 1.9 }}>
                      {shown.unassigned_order_ids.join("  ·  ")}
                    </div>
                    <div className="help-note">No feasible truck had spare capacity in time. Open another algorithm to see who (if anyone) serves these.</div>
                  </>
                )}
              </>
            ) : (
              <div className="empty-state"><span className="spinner" /> solving…</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
