import { useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import ControlPanel from "./components/ControlPanel";
import AlgorithmPage from "./components/AlgorithmPage";
import ComparePage from "./components/ComparePage";
import HybridLab from "./components/HybridLab";
import SimulatorPage from "./components/SimulatorPage";
import type { SimEntry } from "./components/SimulatorPage";
import ExplanationDrawer from "./components/ExplanationDrawer";
import type {
  AlgorithmInfo, AllocationResult, Assignment, CompareResult, CostConfig, Scenario,
} from "./types";
import { ALGO_COLORS, ALGO_SHORT } from "./types";

const DEFAULT_WEIGHTS: CostConfig = {
  w_dist: 2, w_late: 2, w_idle: 5, w_prio: 8, w_unassigned: 100, circuity_factor: 1.3,
};

const ALGO_TABS = ["greedy", "hungarian", "min_cost_flow"];
const SIM_PROFILES: [string, string][] = [
  ["contested", "Contested — orders clustered on few trucks"],
  ["abundant", "Abundant — trucks ≫ orders, dispersed"],
  ["scarce", "Scarce — fewer trucks than orders"],
  ["tight_windows", "Tight windows — narrow deadlines"],
  ["batching", "Batching — trucks carry several orders"],
];
const TABS: { key: string; label: string; kind: string }[] = [
  { key: "greedy", label: "Greedy", kind: "01" },
  { key: "hungarian", label: "Hungarian", kind: "02" },
  { key: "min_cost_flow", label: "Min-Cost Flow", kind: "03" },
  { key: "compare", label: "Compare All", kind: "04" },
  { key: "hybrid", label: "Hybrid Lab", kind: "⊕" },
  { key: "simulator", label: "Simulator", kind: "⊞" },
];
const TAB_COLOR = (k: string) =>
  k === "compare" ? "#ffb000" : k === "hybrid" ? "#7bdcff"
    : k === "simulator" ? "#9be8ff" : ALGO_COLORS[k];

export default function App() {
  const [algorithms, setAlgorithms] = useState<AlgorithmInfo[]>([]);
  const [tab, setTab] = useState("greedy");

  // shared scenario config
  const [profile, setProfile] = useState("contested");
  const [nTrucks, setNTrucks] = useState(8);
  const [nOrders, setNOrders] = useState(12);
  const [seed, setSeed] = useState(7);
  const [weights, setWeights] = useState<CostConfig>(DEFAULT_WEIGHTS);
  const [scenario, setScenario] = useState<Scenario | null>(null);

  // per-mode results
  const [single, setSingle] = useState<Record<string, AllocationResult>>({});
  const [compare, setCompare] = useState<CompareResult | null>(null);
  const [compareSel, setCompareSel] = useState<string[]>([...ALGO_TABS]);
  const [focus, setFocus] = useState("hungarian");
  const [primary, setPrimary] = useState("hungarian");
  const [secondary, setSecondary] = useState("greedy");
  const [hybrid, setHybrid] = useState<{
    combined: AllocationResult; primaryAlone: AllocationResult; secondaryAlone: AllocationResult;
  } | null>(null);
  const [simSel, setSimSel] = useState<string[]>(["contested", "batching", "abundant"]);
  const [sim, setSim] = useState<Record<string, SimEntry>>({});
  const [simExpanded, setSimExpanded] = useState<string | null>(null);

  const [drawer, setDrawer] = useState<{ algo: string; a: Assignment } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ---- load algorithm metadata once ----
  useEffect(() => { api.listAlgorithms().then(setAlgorithms).catch((e) => setError(String(e))); }, []);

  // ---- (re)generate the scenario whenever its defining inputs change ----
  async function loadScenario() {
    setBusy(true); setError(null);
    try {
      const sc = await api.generate(profile, nTrucks, nOrders, seed);
      setScenario(sc);
      setSingle({}); setCompare(null); setHybrid(null);  // invalidate caches
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }
  useEffect(() => { loadScenario(); /* eslint-disable-next-line */ }, [profile, nTrucks, nOrders, seed]);

  // ---- compute the active tab's result; keyed so it only re-runs when relevant inputs change ----
  const computeKey = useMemo(() => {
    if (!scenario) return "";
    const w = JSON.stringify(weights);
    if (tab === "compare") return `cmp|${scenario.id}|${w}|${[...compareSel].sort().join(",")}`;
    if (tab === "hybrid") return `hyb|${scenario.id}|${w}|${primary}|${secondary}`;
    if (tab === "simulator") return `sim|${[...simSel].sort().join(",")}|${nTrucks}|${nOrders}|${seed}|${w}`;
    return `one|${tab}|${scenario.id}|${w}`;
  }, [scenario, tab, weights, compareSel, primary, secondary, simSel, nTrucks, nOrders, seed]);

  useEffect(() => {
    if (!scenario || !computeKey) return;
    let cancelled = false;
    (async () => {
      setBusy(true); setError(null);
      try {
        if (tab === "compare") {
          const sel = compareSel.length ? compareSel : [...ALGO_TABS];
          const cmp = await api.compare(scenario.id, sel, weights);
          if (cancelled) return;
          setCompare(cmp);
          if (!sel.includes(focus)) setFocus(sel[0]);
        } else if (tab === "hybrid") {
          const [combined, primaryAlone, secondaryAlone] = await Promise.all([
            api.hybrid(scenario.id, primary, secondary, weights),
            api.allocate(scenario.id, primary, weights),
            api.allocate(scenario.id, secondary, weights),
          ]);
          if (cancelled) return;
          setHybrid({ combined, primaryAlone, secondaryAlone });
        } else if (tab === "simulator") {
          const entries = await Promise.all(simSel.map(async (pf) => {
            const sc = await api.generate(pf, nTrucks, nOrders, seed);
            const cmp = await api.compare(sc.id, ALGO_TABS, weights);
            return [pf, { scenario: sc, compare: cmp }] as const;
          }));
          if (cancelled) return;
          setSim(Object.fromEntries(entries));
        } else {
          // single algo — run via compare against hungarian so the gap is filled
          const algos = tab === "hungarian" ? ["hungarian"] : [tab, "hungarian"];
          const cmp = await api.compare(scenario.id, algos, weights);
          if (cancelled) return;
          setSingle((m) => ({ ...m, [tab]: cmp.results[tab] }));
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line
  }, [computeKey]);

  const toggleCmp = (k: string) =>
    setCompareSel((s) => (s.includes(k) ? s.filter((x) => x !== k) : [...s, k]));

  const accent = TAB_COLOR(tab);
  const isAlgo = ALGO_TABS.includes(tab);
  const runLabel = tab === "compare" ? "▶ Compare"
    : tab === "hybrid" ? "▶ Run hybrid"
    : tab === "simulator" ? "▶ Run simulation"
    : `▶ Run ${ALGO_SHORT[tab]}`;

  return (
    <div className="app" style={{ ["--accent" as string]: accent }}>
      <div className="topbar">
        <span className="brand"><span className="logo" /> Dispatch<span className="dot">.</span>Engine</span>
        <span className="tagline">Resource Allocation · Delivery Fleet</span>
        <span className="spacer" />
        <span className="status-led">
          <span className={`led ${busy ? "busy" : error ? "err" : ""}`} />
          {busy ? "solving" : error ? "error" : "ready"}
        </span>
      </div>

      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t.key}
            className={`tab ${tab === t.key ? "active" : ""}`}
            style={{ ["--tab-c" as string]: TAB_COLOR(t.key) }}
            onClick={() => setTab(t.key)}>
            <span className="swatch" />
            {t.label}
            <span className="kind">{t.kind}</span>
          </button>
        ))}
      </nav>

      <ControlPanel
        profile={profile} setProfile={setProfile}
        nTrucks={nTrucks} setNTrucks={setNTrucks}
        nOrders={nOrders} setNOrders={setNOrders}
        seed={seed} setSeed={setSeed}
        weights={weights} setWeights={setWeights}
        onRun={loadScenario} busy={busy} runLabel={runLabel}
        showProfile={tab !== "simulator"}
      >
        {tab === "compare" && (
          <>
            <span className="label">Algorithms</span>
            <div className="chips">
              {algorithms.map((a) => {
                const on = compareSel.includes(a.key);
                return (
                  <div key={a.key} className={`chip ${on ? "on" : ""}`}
                    style={{ ["--chip-c" as string]: ALGO_COLORS[a.key] }}
                    onClick={() => toggleCmp(a.key)}
                    title={`${a.optimality} · ${a.complexity}`}>
                    <span className="swatch" />
                    <span>{ALGO_SHORT[a.key] ?? a.name}</span>
                    <span className="meta">{a.complexity}</span>
                  </div>
                );
              })}
            </div>
          </>
        )}
        {tab === "hybrid" && (
          <div className="help-note" style={{ marginTop: 0 }}>
            Pick the two strategies to stack on the Hybrid&nbsp;Lab page →
          </div>
        )}
        {tab === "simulator" && (
          <div className="help-note" style={{ marginTop: 0 }}>
            These trucks / orders / weights apply to every simulated scenario. Pick which scenarios to
            run on the Simulator page →
          </div>
        )}
        {isAlgo && (
          <div className="help-note" style={{ marginTop: 0 }}>
            Showing one algorithm. Switch tabs above to compare, or open the&nbsp;Hybrid&nbsp;Lab.
          </div>
        )}
      </ControlPanel>

      <main className="main">
        {error && <div className="error-banner">⚠ {error}</div>}

        {isAlgo && (
          <AlgorithmPage
            algoKey={tab}
            info={algorithms.find((a) => a.key === tab)}
            scenario={scenario}
            weights={weights}
            result={single[tab] ?? null}
            busy={busy}
            onPick={(a) => setDrawer({ algo: tab, a })}
          />
        )}

        {tab === "compare" && (
          <ComparePage
            scenario={scenario}
            compare={compare}
            focus={focus} setFocus={setFocus}
            busy={busy}
            onPick={(algo, a) => setDrawer({ algo, a })}
          />
        )}

        {tab === "hybrid" && (
          <HybridLab
            algorithms={algorithms}
            scenario={scenario}
            weights={weights}
            primary={primary} setPrimary={setPrimary}
            secondary={secondary} setSecondary={setSecondary}
            combined={hybrid?.combined ?? null}
            primaryAlone={hybrid?.primaryAlone ?? null}
            secondaryAlone={hybrid?.secondaryAlone ?? null}
            busy={busy}
            onPick={(a) => setDrawer({ algo: "hybrid", a })}
          />
        )}

        {tab === "simulator" && (
          <SimulatorPage
            profiles={SIM_PROFILES}
            selected={simSel}
            toggle={(k) => setSimSel((s) => s.includes(k) ? s.filter((x) => x !== k) : [...s, k])}
            results={sim}
            busy={busy}
            expanded={simExpanded} setExpanded={setSimExpanded}
            onPick={(algo, a) => setDrawer({ algo, a })}
          />
        )}
      </main>

      {drawer && (
        <ExplanationDrawer algo={drawer.algo} assignment={drawer.a}
          onClose={() => setDrawer(null)} />
      )}
    </div>
  );
}
