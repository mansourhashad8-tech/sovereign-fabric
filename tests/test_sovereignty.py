from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.contract import REQUIREMENTS
from sovereign.evolution import EvolutionEngine
from sovereign.sovereignty import SovereigntyProtocol
from sovereign.store import FabricStore


def _system():
    store = FabricStore()
    engine = EvolutionEngine(store, experts=[])
    return store, SovereigntyProtocol(engine)


def test_fusion_is_functional_not_metaphysical():
    store, system = _system()
    try:
        fused = system.fusion.fuse()
        assert fused["domain_count"] == 10
        assert fused["cohesion"] == 1.0
        assert fused["functional_composition"] is True
        assert fused["metaphysical_unity"] is False
        assert fused["links"]
        assert fused["single_entrypoints"]
    finally:
        store.close()


def test_audit_keeps_absolute_claims_false():
    store, system = _system()
    try:
        audit = system.audit()
        assert audit["functional_fusion"] is True
        assert audit["absolute_sovereignty"] is False
        assert audit["cosmic_determinism"] is False
        assert audit["ontological_perfection"] is False
        assert audit["literal_met"] == 0
        assert audit["non_claims"]
    finally:
        store.close()


def test_plan_is_deterministic_but_not_guaranteed():
    store, system = _system()
    try:
        solved = system.plan("markdown")
        assert solved["solved"] is True
        assert solved["deterministic_search"] is True
        assert solved["guaranteed_success"] is False
        assert solved["steps"]
        missing = system.plan("does.not.exist")
        assert missing["solved"] is False
        assert "synthesize" in missing["next_action"]
    finally:
        store.close()


def test_perfection_step_is_bounded_and_measured():
    store, system = _system()
    try:
        step = system.perfection(execute=False)
        assert step["executed"] is False
        assert step["perfection_claim"] is False
        assert step["unbounded_loop"] is False
        assert step["choice"]["goal"]
    finally:
        store.close()


def test_contract_records_fusion_and_absolute_gaps():
    by_id = {item["id"]: item for item in REQUIREMENTS}
    assert by_id["capability_fusion"]["status"] == "met"
    assert by_id["absolute_sovereignty"]["status"] == "false"
    assert by_id["dynamic_perfection"]["status"] == "partial"
    assert by_id["cosmic_determinism"]["status"] == "false"
    assert by_id["ontological_perfection"]["status"] == "false"
    assert by_id["no_failure_no_delay"]["status"] == "false"


def test_sovereignty_api_reports_fusion_and_false_absolutes():
    client = TestClient(create_app())
    fused = client.get("/sovereignty/fusion")
    assert fused.status_code == 200
    assert fused.json()["metaphysical_unity"] is False

    audit = client.get("/sovereignty/audit")
    assert audit.status_code == 200
    assert audit.json()["absolute_sovereignty"] is False

    status = client.get("/sovereignty/status")
    assert status.status_code == 200
    assert status.json()["contract"]["total"] == len(REQUIREMENTS)

    plan = client.post("/sovereignty/plan", json={"goal": "markdown"})
    assert plan.status_code == 200
    assert plan.json()["guaranteed_success"] is False

    perfection = client.post("/sovereignty/perfection", json={"execute": False})
    assert perfection.status_code == 200
    assert perfection.json()["perfection_claim"] is False
