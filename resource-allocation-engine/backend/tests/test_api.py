"""API integration tests using FastAPI's TestClient."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_lists_algorithms():
    r = client.get("/")
    assert r.status_code == 200
    assert "greedy" in r.json()["algorithms"]


def test_algorithms_metadata():
    r = client.get("/algorithms")
    assert r.status_code == 200
    keys = {a["key"] for a in r.json()}
    assert keys == {"greedy", "hungarian", "min_cost_flow"}


def test_generate_and_allocate():
    g = client.post("/scenarios/generate",
                    json={"profile": "contested", "n_trucks": 6, "n_orders": 8, "seed": 3})
    assert g.status_code == 200
    sid = g.json()["id"]

    a = client.post("/allocate", json={"scenario_id": sid, "algorithm": "hungarian"})
    assert a.status_code == 200
    body = a.json()
    assert body["algorithm"] == "hungarian"
    assert "metrics" in body and body["metrics"]["total_orders"] == 8
    # every assignment carries an explanation
    for asn in body["assignments"]:
        assert "explanation" in asn
        assert "breakdown" in asn["explanation"]


def test_compare_fills_optimality_gap():
    g = client.post("/scenarios/generate",
                    json={"profile": "scarce", "n_trucks": 7, "n_orders": 12, "seed": 7})
    sid = g.json()["id"]
    c = client.post("/allocate/compare",
                    json={"scenario_id": sid,
                          "algorithms": ["greedy", "hungarian", "min_cost_flow"]})
    assert c.status_code == 200
    results = c.json()["results"]
    assert results["hungarian"]["metrics"]["optimality_gap"] == 0.0
    # greedy should not be better than the optimal baseline on the objective
    assert results["greedy"]["metrics"]["optimality_gap"] >= -1e-6


def test_hybrid_endpoint_returns_combined_result():
    g = client.post("/scenarios/generate",
                    json={"profile": "batching", "n_trucks": 8, "n_orders": 12, "seed": 7})
    sid = g.json()["id"]
    h = client.post("/allocate/hybrid",
                    json={"scenario_id": sid, "primary": "hungarian", "secondary": "greedy"})
    assert h.status_code == 200
    body = h.json()
    assert body["algorithm"] == "hybrid:hungarian+greedy"
    # batching: the fill phase should lift coverage past one-to-one Hungarian
    hu = client.post("/allocate", json={"scenario_id": sid, "algorithm": "hungarian"}).json()
    assert body["metrics"]["assigned_count"] > hu["metrics"]["assigned_count"]
    # phase labelling survives serialisation
    notes = [a["explanation"].get("note", "") for a in body["assignments"]]
    assert any("Phase 2" in (n or "") for n in notes)


def test_hybrid_unknown_algorithm_422():
    g = client.post("/scenarios/generate", json={"profile": "abundant", "seed": 1})
    sid = g.json()["id"]
    r = client.post("/allocate/hybrid",
                    json={"scenario_id": sid, "primary": "greedy", "secondary": "bogus"})
    assert r.status_code == 422


def test_unknown_scenario_404():
    r = client.post("/allocate", json={"scenario_id": "nope", "algorithm": "greedy"})
    assert r.status_code == 404


def test_unknown_algorithm_422():
    g = client.post("/scenarios/generate", json={"profile": "abundant", "seed": 1})
    sid = g.json()["id"]
    r = client.post("/allocate", json={"scenario_id": sid, "algorithm": "bogus"})
    assert r.status_code == 422


def test_interactive_add_truck_and_order():
    g = client.post("/scenarios/generate",
                    json={"profile": "abundant", "n_trucks": 4, "n_orders": 4, "seed": 2})
    sid = g.json()["id"]
    n_trucks_before = len(g.json()["trucks"])
    t = client.post(f"/scenarios/{sid}/trucks", json={
        "id": "T-NEW", "location": {"lat": 19.07, "lon": 72.87},
        "capacity_weight_kg": 2000, "capacity_volume_m3": 12, "capabilities": [],
        "shift_start": "2026-01-15T06:00:00Z", "shift_end": "2026-01-15T18:00:00Z",
    })
    assert t.status_code == 200
    assert len(t.json()["trucks"]) == n_trucks_before + 1
