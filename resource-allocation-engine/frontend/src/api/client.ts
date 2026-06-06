// Thin fetch wrapper over the FastAPI backend. In dev, Vite proxies /api -> :8000.
import type {
  AlgorithmInfo, AllocationResult, CompareResult, CostConfig, Scenario,
} from "../types";

const BASE = "/api";

async function jx<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* ignore */ }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listAlgorithms: () => jx<AlgorithmInfo[]>("/algorithms"),

  generate: (profile: string, n_trucks: number, n_orders: number, seed: number) =>
    jx<Scenario>("/scenarios/generate", {
      method: "POST",
      body: JSON.stringify({ profile, n_trucks, n_orders, seed }),
    }),

  getScenario: (id: string) => jx<Scenario>(`/scenarios/${id}`),

  compare: (scenario_id: string, algorithms: string[], weights?: CostConfig) =>
    jx<CompareResult>("/allocate/compare", {
      method: "POST",
      body: JSON.stringify({ scenario_id, algorithms, weights }),
    }),

  allocate: (scenario_id: string, algorithm: string, weights?: CostConfig) =>
    jx<AllocationResult>("/allocate", {
      method: "POST",
      body: JSON.stringify({ scenario_id, algorithm, weights }),
    }),

  hybrid: (scenario_id: string, primary: string, secondary: string, weights?: CostConfig) =>
    jx<AllocationResult>("/allocate/hybrid", {
      method: "POST",
      body: JSON.stringify({ scenario_id, primary, secondary, weights }),
    }),
};
