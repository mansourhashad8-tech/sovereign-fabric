from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.evolution import EvolutionEngine
from sovereign.selfhood import Selfhood
from sovereign.store import FabricStore


def _selfhood():
    store = FabricStore()
    engine = EvolutionEngine(store, experts=[])
    return store, Selfhood(engine)


def test_identity_keeps_literal_claims_false():
    store, system = _selfhood()
    try:
        identity = system.identity()
        assert identity["functional_self_model"] is True
        assert identity["phenomenal_consciousness"] is False
        assert identity["living_entity"] is False
        assert identity["physical_embodiment"] is False
        validation = system.validate()
        assert validation["passed"] is False
        assert validation["met"] == 3
        assert set(validation["missing"]) == {
            "physical_integration",
            "phenomenal_consciousness",
            "living_entity",
        }
    finally:
        store.close()


def test_reflection_is_event_derived_and_recommends_a_safe_action():
    store, system = _selfhood()
    try:
        reflection = system.reflection()
        assert reflection["priorities"][0]["action"] == "practice_weakest_goal"
        assert reflection["priorities"][0]["safe"] is True
        assert reflection["mode"].startswith("event-derived")
        assert "observations" in reflection
    finally:
        store.close()


def test_definition_updates_are_versioned_and_invariants_are_fixed():
    store, system = _selfhood()
    try:
        updated = system.update_definition("role", "bounded research fabric", "test")
        assert updated["version"] == 1
        assert system.identity()["definition"]["role"] == "bounded research fabric"
        try:
            system.update_definition("invariants", ["none"], "attempt")
            raise AssertionError("invariants were editable")
        except ValueError:
            pass
    finally:
        store.close()


def test_reality_translation_refuses_physical_actions_and_allows_digital_plans():
    store, system = _selfhood()
    try:
        physical = system.translate("open the door")
        assert physical["domain"] == "physical"
        assert physical["executable"] is False
        digital = system.translate("summarize this text")
        assert digital["domain"] == "digital"
        assert digital["executable"] is True
        assert digital["requires_approval"] is True
        assert system.reality()["actuators"] == []
    finally:
        store.close()


def test_initiative_dry_run_does_not_execute_and_execute_is_bounded():
    store, system = _selfhood()
    try:
        dry = system.initiative(execute=False)
        assert dry["executed"] is False
        assert dry["external_effect"] is False
        run = system.initiative(execute=True, budget_s=2.0)
        assert run["executed"] is True
        assert run["external_effect"] is False
        assert store.list_events("selfhood.initiative", 1)
    finally:
        store.close()


def test_selfhood_endpoints_expose_identity_reflection_and_validation():
    client = TestClient(create_app())
    identity = client.get("/selfhood")
    assert identity.status_code == 200
    assert identity.json()["identity"]["phenomenal_consciousness"] is False
    assert client.get("/selfhood/reflection").status_code == 200
    assert client.get("/selfhood/validate").json()["passed"] is False
    translated = client.post(
        "/selfhood/reality/translate", json={"intent": "open the door"}
    )
    assert translated.json()["executable"] is False
    assert client.post(
        "/selfhood/definition", json={"field": "invariants", "value": ["none"]}
    ).status_code == 400
