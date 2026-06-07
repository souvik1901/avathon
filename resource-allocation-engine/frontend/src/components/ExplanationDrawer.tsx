import type { Assignment } from "../types";
import { ALGO_COLORS, ALGO_SHORT } from "../types";

interface Props {
  algo: string;
  assignment: Assignment;
  onClose: () => void;
}

const BREAKDOWN: [string, keyof Assignment["explanation"]["breakdown"], string][] = [
  ["Distance", "distance", "var(--amber)"],
  ["Lateness", "lateness", "var(--red)"],
  ["Idle / underuse", "idle", "var(--cyan)"],
  ["Priority bonus", "priority", "var(--green)"],
];

export default function ExplanationDrawer({ algo, assignment, onClose }: Props) {
  const ex = assignment.explanation;
  const b = ex.breakdown;
  const mag = Math.max(
    1, Math.abs(b.distance), Math.abs(b.lateness), Math.abs(b.idle), Math.abs(b.priority),
  );

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <div className="drawer">
        <div className="drawer-head">
          <span className="swatch" style={{
            width: 12, height: 12, borderRadius: 2, marginRight: 10,
            background: ALGO_COLORS[algo], display: "inline-block",
          }} />
          <h3>{assignment.truck_id} → {assignment.order_id}</h3>
          <button className="x" onClick={onClose}>×</button>
        </div>
        <div className="drawer-body">
          <div className="subtle" style={{ marginBottom: 10 }}>
            {ALGO_SHORT[algo] ?? algo} decision
          </div>

          <div className="kv"><span className="k">Total cost</span>
            <span className="mono">{assignment.cost.toFixed(2)}</span></div>
          <div className="kv"><span className="k">Travel</span>
            <span className="mono">{assignment.travel_km.toFixed(2)} km</span></div>
          <div className="kv"><span className="k">ETA</span>
            <span className="mono">{new Date(assignment.eta).toUTCString().slice(17, 22)}</span></div>
          <div className="kv"><span className="k">Predicted lateness</span>
            <span className="mono" style={{ color: assignment.predicted_lateness_min > 0 ? "var(--red)" : "var(--green)" }}>
              {assignment.predicted_lateness_min.toFixed(1)} min</span></div>

          <div className="subtle" style={{ margin: "16px 0 8px" }}>COST BREAKDOWN</div>
          {BREAKDOWN.map(([lbl, key, color]) => {
            const v = b[key];
            return (
              <div key={key} style={{ marginBottom: 8 }}>
                <div className="kv" style={{ borderBottom: "none", padding: "2px 0" }}>
                  <span className="k">{lbl}</span>
                  <span className="mono">{v.toFixed(2)}</span>
                </div>
                <div className="bar">
                  <span style={{ width: `${(Math.abs(v) / mag) * 100}%`, background: color }} />
                </div>
              </div>
            );
          })}

          {ex.runner_up_truck_id && (
            <>
              <div className="subtle" style={{ margin: "16px 0 8px" }}>COUNTERFACTUAL</div>
              <div className="kv"><span className="k">Next-best truck</span>
                <span className="mono">{ex.runner_up_truck_id}</span></div>
              <div className="kv"><span className="k">Its cost</span>
                <span className="mono">{ex.runner_up_cost?.toFixed(2)}</span></div>
              <div className="kv"><span className="k">Opportunity cost</span>
                <span className="mono" style={{ color: "var(--amber)" }}>
                  +{ex.runner_up_delta?.toFixed(2)}</span></div>
            </>
          )}

          {ex.note && <div className="note">{ex.note}</div>}

          {ex.rejected.length > 0 && (
            <>
              <div className="subtle" style={{ margin: "16px 0 8px" }}>
                REJECTED TRUCKS ({ex.rejected.length})
              </div>
              {ex.rejected.map((r) => (
                <div className="reject" key={r.truck_id}>
                  <span className="tid">{r.truck_id}</span>
                  <span>{r.reason}</span>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </>
  );
}
