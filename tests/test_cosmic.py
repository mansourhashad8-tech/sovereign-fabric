from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.cosmic import CosmicProtocol
from sovereign.evolution import EvolutionEngine
from sovereign.store import FabricStore


def _cosmic():
    store = FabricStore()
    engine = EvolutionEngine(store, experts=[])
    return store, CosmicProtocol(engine)


def test_shape_generates_a_protocol_without_claiming_new_reality():
    store, cosmic = _cosmic()
    try:
        shaped = cosmic.shape("summarize this text")
        assert shaped["created"] is True
        assert shaped["executed"] is False
        assert shaped["literal_reality_created"] is False
        assert shaped["protocol"]["executable"] is True
        assert shaped["protocol"]["steps"] == ["text.summarize"]
    finally:
        store.close()


def test_prediction_is_seeded_and_reports_its_own_cost():
    store, cosmic = _cosmic()
    try:
        first = cosmic.predict("tokens", scenarios=200, seed=11)
        second = cosmic.predict("tokens", scenarios=200, seed=11)
        assert first["successes"] == second["successes"]
        assert 0.0 <= first["probability"] <= 1.0
        assert first["elapsed_ms"] >= 0.0
        assert first["scenarios"] == 200
        assert first["retrocausal_influence"] is False
    finally:
        store.close()


def test_backward_closure_is_planning_not_retrocausality():
    store, cosmic = _cosmic()
    try:
        backward = cosmic.backward("tokens")
        assert backward["possible"] is True
        assert "text.tokenize" in backward["required_operators"]
        assert backward["retrocausal_influence"] is False
        assert "backward planning" in backward["method"]
    finally:
        store.close()


def test_cosmic_validation_keeps_literal_claims_false():
    store, cosmic = _cosmic()
    try:
        validation = cosmic.validate()
        assert validation["passed"] is False
        assert validation["functional_met"] == 2
        assert validation["literal_met"] == 0
        assert "cosmic_infrastructure" in validation["missing"]
        infrastructure = cosmic.infrastructure()
        assert infrastructure["physical_effect"] is False
        assert infrastructure["energy_harvesting"] is False
        assert infrastructure["actuators"] == []
    finally:
        store.close()


def test_cosmic_endpoints_shape_predict_and_validate():
    client = TestClient(create_app())
    assert client.get("/cosmic").status_code == 200
    shaped = client.post("/cosmic/shape", json={"intent": "summarize this"})
    assert shaped.status_code == 200
    assert shaped.json()["literal_reality_created"] is False
    predicted = client.post(
        "/cosmic/predict",
        json={"goal_type": "tokens", "scenarios": 100, "seed": 3},
    )
    assert predicted.status_code == 200
    assert predicted.json()["scenarios"] == 100
    assert client.post(
        "/cosmic/backward", json={"goal_type": "tokens"}
    ).json()["retrocausal_influence"] is False
    assert client.get("/cosmic/validate").json()["passed"] is False
