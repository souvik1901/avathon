import type { ReactNode } from "react";
import type { CostConfig } from "../types";

interface Props {
  profile: string; setProfile: (p: string) => void;
  nTrucks: number; setNTrucks: (n: number) => void;
  nOrders: number; setNOrders: (n: number) => void;
  seed: number; setSeed: (n: number) => void;
  weights: CostConfig; setWeights: (w: CostConfig) => void;
  onRun: () => void; busy: boolean;
  runLabel?: string;
  showProfile?: boolean;   // hide the single-profile picker on Simulator
  children?: ReactNode;    // mode-specific controls (algo chips, etc.)
}

const PROFILES: [string, string][] = [
  ["contested", "Contested — orders clustered on few trucks"],
  ["abundant", "Abundant — trucks ≫ orders, dispersed"],
  ["scarce", "Scarce — fewer trucks than orders"],
  ["tight_windows", "Tight windows — narrow deadlines"],
  ["batching", "Batching — trucks carry several orders"],
];

const PROFILE_DESC: Record<string, string> = {
  contested: "Demand piles onto two hubs while the fleet is spread out — many orders chase a few nearby trucks. Greedy strands orders here; global methods pull ahead.",
  abundant: "Far more trucks than orders, dispersed across the metro. Almost every order has a nearby idle truck, so greedy is near-optimal.",
  scarce: "Fewer trucks than orders — some orders simply can't be served. Watch coverage and which priorities get protected.",
  tight_windows: "Very short deadlines. Distant trucks can't arrive in time, so lateness and feasibility dominate.",
  batching: "Trucks carry up to 3 orders and demand clusters on adjacent hubs — the regime where Min-Cost Flow and the Hybrid consolidate and win.",
};

// [key, label, min, max, step, description]
const WEIGHTS: [keyof CostConfig, string, number, number, number, string][] = [
  ["w_dist", "Distance", 0, 10, 0.5, "Cost per km travelled (× the truck's cost/km). Higher → prefer nearer trucks, shorter routes."],
  ["w_late", "Lateness", 0, 20, 0.5, "Cost per minute past an order's due-by. Higher → protect deadlines even at extra travel."],
  ["w_idle", "Idle / underuse", 0, 30, 1, "Penalty for wasted capacity (a big truck on a tiny order). Higher → right-size the vehicle."],
  ["w_prio", "Priority bonus", 0, 20, 0.5, "Bonus per priority point — makes urgent orders cheaper to serve, biasing the search toward them."],
  ["w_unassigned", "Unassigned penalty", 0, 300, 10, "Flat cost for every order left unserved. Higher → push coverage up even when serving is expensive."],
  ["circuity_factor", "Road circuity", 1, 2, 0.05, "Straight-line km × this ≈ road km (1.3 ≈ a typical road detour over the crow-flies distance)."],
];

export default function ControlPanel(p: Props) {
  const showProfile = p.showProfile ?? true;
  return (
    <div className="sidebar">
      <div className="section">
        <span className="label">Scenario</span>
        {showProfile && (
          <>
            <div className="field">
              <label>Profile</label>
              <select value={p.profile} onChange={(e) => p.setProfile(e.target.value)}>
                {PROFILES.map(([k, desc]) => <option key={k} value={k}>{desc}</option>)}
              </select>
            </div>
            <div className="profile-desc">{PROFILE_DESC[p.profile]}</div>
          </>
        )}
        <div className="row">
          <div className="field">
            <label>Trucks</label>
            <input type="number" min={1} max={200} value={p.nTrucks}
              onChange={(e) => p.setNTrucks(+e.target.value)} />
          </div>
          <div className="field">
            <label>Orders</label>
            <input type="number" min={1} max={400} value={p.nOrders}
              onChange={(e) => p.setNOrders(+e.target.value)} />
          </div>
          <div className="field">
            <label>Seed</label>
            <input type="number" value={p.seed}
              onChange={(e) => p.setSeed(+e.target.value)} />
          </div>
        </div>
        <div className="help-note">
          Same seed ⇒ identical trucks &amp; orders (reproducible). Profiles place points on real
          Kolkata-metro land hubs.
        </div>
      </div>

      {p.children && <div className="section">{p.children}</div>}

      <div className="section">
        <span className="label">Cost weights</span>
        <div className="help-note" style={{ marginTop: 0, marginBottom: 10 }}>
          cost = dist·km + late·min + idle·slack − prio·priority · objective adds the unassigned penalty
        </div>
        {WEIGHTS.map(([key, lbl, min, max, step, desc]) => (
          <div className="weight" key={key}>
            <div className="slider-row">
              <label title={desc}>{lbl}</label>
              <input type="range" min={min} max={max} step={step}
                value={p.weights[key] as number}
                onChange={(e) => p.setWeights({ ...p.weights, [key]: +e.target.value })} />
              <span className="val">{(p.weights[key] as number).toFixed(key === "circuity_factor" ? 2 : 1)}</span>
            </div>
            <div className="weight-desc">{desc}</div>
          </div>
        ))}
      </div>

      <button className="run" onClick={p.onRun} disabled={p.busy}>
        {p.busy ? "Solving…" : (p.runLabel ?? "▶ Run")}
      </button>
    </div>
  );
}
