from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.evolution import EvolutionEngine
from sovereign.store import FabricStore
from sovereign.transformation import TransformationEngine


def _system():
    store = FabricStore()
    engine = EvolutionEngine(store, experts=[])
    return store, TransformationEngine(engine)


def test_digital_transformation_has_one_trace_and_no_absolute_claim():
    store, system = _system()
    try:
        trace = system.execute("summarize this text", mode="digital", budget_s=5)
        assert trace["mode"] == "digital"
        assert trace["plan"]["solved"] is True
        assert trace["executed"] is True
        assert trace["validated"] is True
        assert trace["literal_transformation"] is False
        assert trace["physical_built"] is False
        assert trace["guaranteed_success"] is False
    finally:
        store.close()


def test_physical_intent_selects_design_only_materialization():
    store, system = _system()
    try:
        trace = system.execute("build a robot arm", mode="auto", quantity=1, budget_usd=100)
        assert trace["mode"] == "material"
        assert trace["status"] == "design_only"
        assert trace["physical_built"] is False
        assert trace["plan"]["materialization_status"] == "design_and_digital_twin_only"
        assert trace["economy"]["sovereign"] is False
    finally:
        store.close()


def test_remote_requires_explicit_authorization():
    store, system = _system()
    try:
        trace = system.execute("run remote tests", mode="remote", execute_remote=False)
        assert trace["status"] == "blocked"
        assert trace["executed"] is False
        assert "execute_remote" in trace["next_action"]
    finally:
        store.close()


def test_status_reports_demand_and_false_absolutes():
    store, system = _system()
    try:
        status = system.status()
        assert status["operational_transformation"] is True
        assert status["literal_transformation"] is False
        assert status["physical_body"] is False
        assert status["sovereignty"]["absolute_sovereignty"] is False
        assert status["demand_summary"]["total"] == 52
    finally:
        store.close()


def test_transform_api_exposes_the_composed_trace():
    client = TestClient(create_app())
    response = client.post(
        "/transform", json={"intent": "summarize this text", "mode": "digital", "budget_s": 5}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["literal_transformation"] is False
    assert body["physical_built"] is False

    status = client.get("/transform/status")
    assert status.status_code == 200
    assert status.json()["literal_transformation"] is False

    self_step = client.post("/transform/self", json={"execute": False})
    assert self_step.status_code == 200
    assert self_step.json()["perfection_claim"] is False
