from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.evolution import EvolutionEngine
from sovereign.metacurriculum import MetaCurriculum
from sovereign.store import FabricStore


def test_table_ranks_weak_uncertain_goals_and_is_deterministic():
    store = FabricStore()
    engine = EvolutionEngine(store, experts=[])
    try:
        first = MetaCurriculum(engine).table(scenarios=20)
        second = MetaCurriculum(engine).table(scenarios=20)
        assert first == second
        assert len(first) == 13
        assert first[0]["priority"] >= first[-1]["priority"]
        assert all("predicted_success" in row for row in first)
    finally:
        store.close()


def test_run_executes_one_measured_practice_and_records_it():
    store = FabricStore()
    engine = EvolutionEngine(store, experts=[])
    try:
        result = MetaCurriculum(engine).run(iterations=1, budget_s=2.0, scenarios=20)
        assert len(result["runs"]) == 1
        run = result["runs"][0]
        assert run["goal"]
        assert "ok" in run
        assert "before_rate" in run
        assert result["note"].startswith("self-directed practice")
        events = store.list_events("meta.practice", 1)
        assert events and events[0]["payload"]["goal"] == run["goal"]
    finally:
        store.close()


def test_meta_curriculum_endpoints_serve_and_run():
    client = TestClient(create_app())
    table = client.get("/curriculum/meta?scenarios=20")
    assert table.status_code == 200
    assert len(table.json()["rows"]) == 13
    run = client.post(
        "/curriculum/meta/run",
        json={"iterations": 1, "budget_s": 2, "scenarios": 20},
    )
    assert run.status_code == 200
    assert len(run.json()["runs"]) == 1
