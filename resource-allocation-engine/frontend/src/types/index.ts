// Types mirroring the backend Pydantic models (app/models.py).

export interface GeoPoint { lat: number; lon: number; }

export interface Truck {
  id: string;
  location: GeoPoint;
  capacity_weight_kg: number;
  capacity_volume_m3: number;
  capabilities: string[];
  shift_start: string;
  shift_end: string;
  avg_speed_kmph: number;
  cost_per_km: number;
  status: string;
  capacity_orders: number;
}

export interface Order {
  id: string;
  pickup: GeoPoint;
  dropoff: GeoPoint;
  weight_kg: number;
  volume_m3: number;
  required_capabilities: string[];
  ready_at: string;
  due_by: string;
  priority: number;
  service_time_min: number;
}

export interface CostConfig {
  w_dist: number;
  w_late: number;
  w_idle: number;
  w_prio: number;
  w_unassigned: number;
  circuity_factor: number;
}

export interface Scenario {
  id: string;
  name: string;
  trucks: Truck[];
  orders: Order[];
  decision_time: string;
  weights: CostConfig;
  seed?: number | null;
}

export interface CostBreakdown {
  distance: number;
  lateness: number;
  idle: number;
  priority: number;
}

export interface RejectedTruck { truck_id: string; reason: string; }

export interface Explanation {
  breakdown: CostBreakdown;
  runner_up_truck_id?: string | null;
  runner_up_cost?: number | null;
  runner_up_delta?: number | null;
  rejected: RejectedTruck[];
  note?: string | null;
}

export interface Assignment {
  truck_id: string;
  order_id: string;
  cost: number;
  eta: string;
  predicted_lateness_min: number;
  travel_km: number;
  explanation: Explanation;
}

export interface Metrics {
  algorithm: string;
  assigned_count: number;
  total_orders: number;
  coverage: number;
  total_cost: number;
  objective: number;
  total_travel_km: number;
  avg_travel_km: number;
  on_time_rate: number;
  avg_lateness_min: number;
  max_lateness_min: number;
  fleet_utilisation: number;
  load_balance_cv: number;
  priority_weighted_fulfilment: number;
  solve_ms: number;
  optimality_gap?: number | null;
}

export interface AllocationResult {
  algorithm: string;
  assignments: Assignment[];
  unassigned_order_ids: string[];
  metrics: Metrics;
}

export interface CompareResult {
  scenario_id: string;
  results: Record<string, AllocationResult>;
}

export interface AlgorithmInfo {
  key: string;
  name: string;
  optimality: string;
  model: string;
  complexity: string;
  best_when: string;
}

export const ALGO_KEYS = ["greedy", "hungarian", "min_cost_flow"] as const;
export type AlgoKey = (typeof ALGO_KEYS)[number];

// Per-algorithm signature colours (sodium-amber, signal-cyan, go-green).
export const ALGO_COLORS: Record<string, string> = {
  greedy: "#ffb000",
  hungarian: "#38d6ff",
  min_cost_flow: "#3ee594",
  hybrid: "#7bdcff",
};

export const ALGO_SHORT: Record<string, string> = {
  greedy: "GREEDY",
  hungarian: "HUNGARIAN",
  min_cost_flow: "MIN-COST FLOW",
  hybrid: "HYBRID",
};

// One-line human label per algorithm for page headers / cards.
export const ALGO_TAGLINE: Record<string, string> = {
  greedy: "Myopic, one order at a time — fast and online",
  hungarian: "Globally optimal one-to-one batch matching",
  min_cost_flow: "Capacitated — one truck can batch several orders",
};

// A short narrative shown on each algorithm's page.
export const ALGO_BLURB: Record<string, string> = {
  greedy:
    "Processes orders in priority order, giving each the cheapest still-available truck. " +
    "No backtracking — an early pick can strand a later order. Near-optimal when resources " +
    "are loose; degrades under contention. The right default for online / streaming dispatch.",
  hungarian:
    "Solves the whole truck↔order matrix at once (Kuhn–Munkres) for the provably cheapest " +
    "one-to-one assignment. This is the baseline every other method is measured against. " +
    "Strictly one truck per order; cubic in problem size.",
  min_cost_flow:
    "Models dispatch as a flow network so one truck can carry several orders (capacity > 1). " +
    "Reduces to Hungarian at capacity 1; beyond that it can cover more orders by consolidating " +
    "— the only method here that captures batching.",
};
