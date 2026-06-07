"""
FastAPI application — the HTTP surface of the Resource Allocation Engine.

Endpoints
  GET  /algorithms                       list strategies + metadata
  POST /scenarios                        create from explicit payload
  POST /scenarios/generate               synthesise from a profile + seed
  GET  /scenarios                        list scenario ids
  GET  /scenarios/{id}                   fetch one
  POST /scenarios/{id}/trucks            interactively add a truck
  POST /scenarios/{id}/orders            interactively add an order
  POST /allocate                         run one algorithm
  POST /allocate/compare                 run several side-by-side (+ optimality gap)

Swagger UI is auto-served at /docs.
"""
from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .engine import run_algorithm, run_comparison, run_hybrid
from .generators import generate_scenario
from .models import (AlgorithmInfo, AllocationResult, CompareResult, CostConfig,
                     Order, Scenario, ScenarioGenerateRequest, Truck)
from .store import InMemoryStore
from .strategies import STRATEGIES

app = FastAPI(title="Resource Allocation Engine", version="1.0.0",
              description="Delivery-fleet resource allocation with comparable "
                          "Greedy / Hungarian / Min-Cost-Flow strategies.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

store = InMemoryStore()


# ---- request bodies -------------------------------------------------------
class AllocateRequest(BaseModel):
    scenario_id: str
    algorithm: str
    weights: CostConfig | None = None


class CompareRequest(BaseModel):
    scenario_id: str
    algorithms: list[str]
    weights: CostConfig | None = None


class HybridRequest(BaseModel):
    scenario_id: str
    primary: str
    secondary: str
    weights: CostConfig | None = None


# ---- helpers --------------------------------------------------------------
def _require(scenario_id: str) -> Scenario:
    sc = store.get(scenario_id)
    if sc is None:
        raise HTTPException(404, f"scenario '{scenario_id}' not found")
    return sc


# ---- algorithms -----------------------------------------------------------
@app.get("/algorithms", response_model=list[AlgorithmInfo])
def list_algorithms() -> list[AlgorithmInfo]:
    return [AlgorithmInfo(key=s.key, name=s.name, optimality=s.optimality,
                          model=s.model, complexity=s.complexity, best_when=s.best_when)
            for s in STRATEGIES.values()]


# ---- scenarios ------------------------------------------------------------
@app.post("/scenarios", response_model=Scenario)
def create_scenario(scenario: Scenario) -> Scenario:
    if not scenario.id:
        scenario.id = f"scn-{uuid.uuid4().hex[:8]}"
    store.put(scenario)
    return scenario


@app.post("/scenarios/generate", response_model=Scenario)
def generate(req: ScenarioGenerateRequest) -> Scenario:
    sc = generate_scenario(req.profile, req.n_trucks, req.n_orders, req.seed, req.name)
    store.put(sc)
    return sc


@app.get("/scenarios", response_model=list[str])
def list_scenarios() -> list[str]:
    return store.list_ids()


@app.get("/scenarios/{scenario_id}", response_model=Scenario)
def get_scenario(scenario_id: str) -> Scenario:
    return _require(scenario_id)


@app.post("/scenarios/{scenario_id}/trucks", response_model=Scenario)
def add_truck(scenario_id: str, truck: Truck) -> Scenario:
    sc = _require(scenario_id)
    sc.trucks.append(truck)
    store.put(sc)
    return sc


@app.post("/scenarios/{scenario_id}/orders", response_model=Scenario)
def add_order(scenario_id: str, order: Order) -> Scenario:
    sc = _require(scenario_id)
    sc.orders.append(order)
    store.put(sc)
    return sc


# ---- allocation -----------------------------------------------------------
@app.post("/allocate", response_model=AllocationResult)
def allocate(req: AllocateRequest) -> AllocationResult:
    sc = _require(req.scenario_id)
    if req.algorithm not in STRATEGIES:
        raise HTTPException(422, f"unknown algorithm '{req.algorithm}'")
    return run_algorithm(sc, req.algorithm, req.weights)


@app.post("/allocate/compare", response_model=CompareResult)
def compare(req: CompareRequest) -> CompareResult:
    sc = _require(req.scenario_id)
    unknown = [a for a in req.algorithms if a not in STRATEGIES]
    if unknown:
        raise HTTPException(422, f"unknown algorithms: {unknown}")
    return run_comparison(sc, req.algorithms, req.weights)


@app.post("/allocate/hybrid", response_model=AllocationResult)
def allocate_hybrid(req: HybridRequest) -> AllocationResult:
    sc = _require(req.scenario_id)
    unknown = [a for a in (req.primary, req.secondary) if a not in STRATEGIES]
    if unknown:
        raise HTTPException(422, f"unknown algorithm(s): {unknown}")
    return run_hybrid(sc, req.primary, req.secondary, req.weights)


@app.get("/")
def root() -> dict:
    return {"service": "resource-allocation-engine", "docs": "/docs",
            "algorithms": list(STRATEGIES.keys())}
