import type { Assignment, CompareResult, Scenario } from "../types";
import { ALGO_COLORS, ALGO_SHORT } from "../types";
import MetricsDashboard from "./MetricsDashboard";
import ComparisonGrid from "./ComparisonGrid";

export interface SimEntry { scenario: Scenario; compare: CompareResult; }

interface Props {
  profiles: [string, string][];      // [key, label]
  selected: string[];
  toggle: (k: string) => void;
  results: Record<string, SimEntry>;
  busy: boolean;
  expanded: string | null;
  setExpanded: (p: string | null) => void;
  onPick: (algo: string, a: Assignment) => void;
}

const SIM_ACCENT = "#9be8ff";

const PROFILE_C: Record<string, string> = {
  contested: "#ffb000", abundant: "#3ee594", scarce: "#ff5d72",
  tight_windows: "#b98bff", batching: "#38d6ff",
};

const NARRATIVE: Record<string, string> = {
  contested: "Two hubs soak up the orders while the fleet is spread out — only the few trucks parked nearby are cheap. Greedy commits early and strands the rest; watch its coverage fall below Hungarian's.",
  abundant: "Trucks outnumber orders and spread across the metro, so nearly every order has a cheap nearby truck. All methods nearly tie and greedy's gap is small.",
  scarce: "There aren't enough trucks for every order, so coverage is capped for everyone. The interesting question is which orders — and which priorities — each method chooses to serve.",
  tight_windows: "Deadlines are so short that distant trucks can't arrive in time. Lateness and feasibility, not raw distance, decide who can be served at all.",
  batching: "Trucks can carry three orders and demand clusters tightly. One-to-one Hungarian caps out; Min-Cost Flow and the Hybrid consolidate and cover far more.",
};

function SummaryCard({ pk, label, entry, onOpen, active }:
  { pk: string; label: string; entry?: SimEntry; onOpen: () => void; active: boolean }) {
  const c = PROFILE_C[pk] ?? SIM_ACCENT;
  const res = entry?.compare.results;
  const algos = res ? Object.keys(res) : [];
  const hu = res?.["hungarian"]?.metrics;
  const greedy = res?.["greedy"]?.metrics;
  const bestCov = res ? Math.max(...algos.map((k) => res[k].metrics.coverage)) : 0;
  const objMax = res ? Math.max(...algos.map((k) => res[k].metrics.objective)) : 1;

  return (
    <button className={`sim-card ${active ? "active" : ""}`} style={{ ["--pc" as string]: c }} onClick={onOpen}>
      <div className="sim-card-head"><span className="dotc" style={{ background: c }} />{label.split("—")[0].trim()}</div>
      {!entry ? (
        <div className="skeleton" style={{ height: 92 }} />
      ) : (
        <>
          <div className="sim-mini">
            <div><span className="mk">best coverage</span><b>{(bestCov * 100).toFixed(0)}%</b></div>
            <div><span className="mk">optimal obj</span><b>{hu ? hu.objective.toFixed(0) : "—"}</b></div>
            <div><span className="mk">greedy gap</span>
              <b style={{ color: (greedy?.optimality_gap ?? 0) > 0 ? "var(--red)" : (greedy?.optimality_gap ?? 0) < 0 ? "var(--green)" : "var(--text-dim)" }}>
                {greedy?.optimality_gap == null ? "—" : `${greedy.optimality_gap > 0 ? "+" : ""}${(greedy.optimality_gap * 100).toFixed(0)}%`}
              </b></div>
          </div>
          <div className="sim-bars">
            {algos.map((k) => (
              <div key={k} className="sim-bar" title={`${ALGO_SHORT[k]} · obj ${res![k].metrics.objective.toFixed(0)}`}>
                <span style={{ height: `${(res![k].metrics.objective / objMax) * 100}%`, background: ALGO_COLORS[k] }} />
              </div>
            ))}
          </div>
          <div className="sim-open">{active ? "▼ showing below" : "click for detail →"}</div>
        </>
      )}
    </button>
  );
}

export default function SimulatorPage(p: Props) {
  const expandedEntry = p.expanded ? p.results[p.expanded] : null;
  const expandedLabel = p.profiles.find(([k]) => k === p.expanded)?.[1] ?? p.expanded;

  return (
    <div className="page" style={{ ["--accent" as string]: SIM_ACCENT }}>
      <div className="hero">
        <div className="glyph">⊞</div>
        <div className="h-body">
          <h2>Simulator — run several scenarios at once</h2>
          <div className="h-tag">Pick the scenarios to simulate · click any card for a full breakdown</div>
          <div className="h-blurb">
            Each selected scenario is generated (with the current truck/order/seed and cost weights) and
            solved by all four algorithms. The cards summarise each at a glance; open one to see the full
            metric matrix, the side-by-side maps, and a note on <i>what's happening and why</i>.
          </div>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 18 }}>
        <div className="panel-head"><h3>Scenarios to simulate</h3>
          <span className="sub">{p.selected.length} selected</span>
          {p.busy && <><span className="spacer" /><span className="spinner" /></>}
        </div>
        <div style={{ padding: 12, display: "flex", flexWrap: "wrap", gap: 8 }}>
          {p.profiles.map(([k, label]) => {
            const on = p.selected.includes(k);
            return (
              <button key={k} className={`sim-chip ${on ? "on" : ""}`}
                style={{ ["--pc" as string]: PROFILE_C[k] }} onClick={() => p.toggle(k)}>
                <span className="dotc" style={{ background: PROFILE_C[k] }} />{label.split("—")[0].trim()}
              </button>
            );
          })}
        </div>
      </div>

      {p.selected.length === 0 ? (
        <div className="empty-state">Select one or more scenarios above to simulate.</div>
      ) : (
        <div className="sim-grid">
          {p.selected.map((k) => (
            <SummaryCard key={k} pk={k}
              label={p.profiles.find(([pk]) => pk === k)?.[1] ?? k}
              entry={p.results[k]}
              active={p.expanded === k}
              onOpen={() => p.setExpanded(p.expanded === k ? null : k)} />
          ))}
        </div>
      )}

      {expandedEntry && (
        <div className="sim-detail">
          <div className="panel" style={{ marginBottom: 16, ["--accent" as string]: PROFILE_C[p.expanded!] ?? SIM_ACCENT }}>
            <div className="panel-head">
              <span className="swatch" style={{ width: 11, height: 11, borderRadius: 3, background: PROFILE_C[p.expanded!] }} />
              <h3>{String(expandedLabel)}</h3>
              <span className="spacer" />
              <button className="x" onClick={() => p.setExpanded(null)}>×</button>
            </div>
            <div className="verdict" style={{ margin: 12, borderColor: "var(--line)" }}>
              <span className="tag">what's happening</span>
              {NARRATIVE[p.expanded!]}
            </div>
          </div>
          <MetricsDashboard compare={expandedEntry.compare} />
          <ComparisonGrid scenario={expandedEntry.scenario} compare={expandedEntry.compare} onPick={p.onPick} />
        </div>
      )}
    </div>
  );
}
