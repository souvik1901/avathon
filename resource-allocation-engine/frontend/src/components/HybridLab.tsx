import type { ReactNode } from "react";
import type { AlgorithmInfo, AllocationResult, Assignment, CostConfig, Scenario } from "../types";
import { ALGO_BLURB, ALGO_COLORS, ALGO_SHORT } from "../types";
import MapView from "./MapView";
import AlgoStats from "./AlgoStats";

interface Props {
  algorithms: AlgorithmInfo[];
  scenario: Scenario | null;
  weights: CostConfig;
  primary: string; setPrimary: (k: string) => void;
  secondary: string; setSecondary: (k: string) => void;
  combined: AllocationResult | null;
  primaryAlone: AllocationResult | null;
  secondaryAlone: AllocationResult | null;
  busy: boolean;
  onPick: (a: Assignment) => void;
}

const HYBRID_ACCENT = "#7bdcff";

export default function HybridLab(p: Props) {
  const keys = p.algorithms.map((a) => a.key);

  const phase2 = p.combined
    ? p.combined.assignments.filter((a) => (a.explanation.note ?? "").includes("Phase 2")).length
    : 0;

  // verdict: did the Phase-2 fill improve on running the primary alone?
  let verdict: { cls: string; text: ReactNode } | null = null;
  if (p.combined && p.primaryAlone && p.secondaryAlone) {
    const c = p.combined.metrics;
    const covGain = c.coverage - p.primaryAlone.metrics.coverage;
    const objGain = p.primaryAlone.metrics.objective - c.objective; // + = hybrid cheaper than primary alone
    if (covGain > 0.001 || objGain > 0.5) {
      verdict = {
        cls: "win",
        text: (
          <>
            <span className="tag">Verdict — combining helps</span>
            Phase 2 ({ALGO_SHORT[p.secondary]}) filled <b>{phase2}</b> order
            {phase2 === 1 ? "" : "s"} that {ALGO_SHORT[p.primary]} left behind, lifting coverage to{" "}
            <b>{(c.coverage * 100).toFixed(0)}%</b>
            {covGain > 0.001 && <> (+{(covGain * 100).toFixed(0)} pts over {ALGO_SHORT[p.primary]} alone)</>} and{" "}
            {objGain > 0.5 ? <>cutting the objective by <b>{objGain.toFixed(0)}</b>.</> : <>holding the objective steady.</>}
          </>
        ),
      };
    } else {
      verdict = {
        cls: "tie",
        text: (
          <>
            <span className="tag">Verdict — no gain here</span>
            With this profile, {ALGO_SHORT[p.primary]} already used every truck it could, so Phase 2
            ({ALGO_SHORT[p.secondary]}) had no spare capacity to fill — the hybrid equals the primary alone.{" "}
            <b>Try the <i>Batching</i> profile</b> (trucks carry several orders), where the second phase has room to add coverage.
          </>
        ),
      };
    }
  }

  const cmpRow = (label: ReactNode, r: AllocationResult | null, highlight = false) => (
    <div className={`cmp-row${highlight ? " combined" : ""}`}>
      <span className="who">{label}</span>
      <span>{r ? `${(r.metrics.coverage * 100).toFixed(0)}% (${r.metrics.assigned_count}/${r.metrics.total_orders})` : "—"}</span>
      <span>{r ? r.metrics.objective.toFixed(0) : "—"}</span>
      <span>{r ? `${r.metrics.solve_ms.toFixed(2)} ms` : "—"}</span>
    </div>
  );

  return (
    <div className="page" style={{ ["--accent" as string]: HYBRID_ACCENT }}>
      <div className="hero">
        <div className="glyph">⊕</div>
        <div className="h-body">
          <h2>Hybrid Lab — combine two strategies</h2>
          <div className="h-tag">Two-phase: primary solves the full problem, secondary fills the leftovers</div>
          <div className="h-blurb">
            <b>Phase 1</b> runs the primary strategy on every order. <b>Phase 2</b> takes the orders it left
            unassigned and lets the secondary strategy place them on whatever truck capacity remains. The
            question this answers: <i>does stacking two methods serve more orders, more cheaply, than either
            alone?</i>
          </div>
        </div>
      </div>

      <div className="hybrid-pick">
        <div className="phase-card" style={{ ["--ph-c" as string]: ALGO_COLORS[p.primary] }}>
          <div className="ph-k">Phase 1 · Primary</div>
          <select value={p.primary} onChange={(e) => p.setPrimary(e.target.value)}>
            {keys.map((k) => <option key={k} value={k}>{ALGO_SHORT[k]}</option>)}
          </select>
          <div className="ph-d">{ALGO_BLURB[p.primary]}</div>
        </div>
        <div className="arrow">→</div>
        <div className="phase-card" style={{ ["--ph-c" as string]: ALGO_COLORS[p.secondary] }}>
          <div className="ph-k">Phase 2 · Fill leftovers</div>
          <select value={p.secondary} onChange={(e) => p.setSecondary(e.target.value)}>
            {keys.map((k) => <option key={k} value={k}>{ALGO_SHORT[k]}</option>)}
          </select>
          <div className="ph-d">{ALGO_BLURB[p.secondary]}</div>
        </div>
      </div>

      {verdict && <div className={`verdict ${verdict.cls}`}>{verdict.text}</div>}

      <div className="panel" style={{ marginBottom: 18 }}>
        <div className="panel-head"><h3>Combined vs each alone</h3>
          <span className="sub">same scenario, same cost weights</span></div>
        <div className="cmp-row head">
          <span>Configuration</span><span>Coverage</span><span>Objective</span><span>Solve time</span>
        </div>
        {cmpRow(<><span className="swatch" style={{ background: HYBRID_ACCENT }} />Hybrid ({ALGO_SHORT[p.primary]} + {ALGO_SHORT[p.secondary]})</>, p.combined, true)}
        {cmpRow(<><span className="swatch" style={{ background: ALGO_COLORS[p.primary] }} />{ALGO_SHORT[p.primary]} alone</>, p.primaryAlone)}
        {cmpRow(<><span className="swatch" style={{ background: ALGO_COLORS[p.secondary] }} />{ALGO_SHORT[p.secondary]} alone</>, p.secondaryAlone)}
      </div>

      {p.combined && <AlgoStats m={p.combined.metrics} accent={HYBRID_ACCENT} />}

      <div className="panel">
        <div className="panel-head">
          <h3>Hybrid routes</h3>
          <span className="sub">click a route — the explanation says which phase placed it</span>
          {p.busy && <><span className="spacer" /><span className="spinner" /></>}
        </div>
        <div style={{ padding: 12 }}>
          {p.scenario && p.combined ? (
            <MapView scenario={p.scenario} assignments={p.combined.assignments}
              color={HYBRID_ACCENT} height={560} onPick={p.onPick} />
          ) : (
            <div className="skeleton" style={{ height: 560 }} />
          )}
        </div>
      </div>
    </div>
  );
}
