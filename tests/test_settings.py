from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.evolution import EvolutionEngine
from sovereign.feedback import feedback_scores
from sovereign.guardians import GuardianRegistry, LocalGuardian
from sovereign.pathfinder import Operator, PathFinder
from sovereign.settings import Settings
from sovereign.store import FabricStore


def test_settings_are_bounded_persisted_and_audited():
    store = FabricStore()
    settings = Settings(store)
    assert settings.get("planner.feedback_scale") == 0.25
    assert settings.set("planner.feedback_scale", 0.3, "measured tune")["new"] == 0.3
    assert Settings(store).get("planner.feedback_scale") == 0.3
    assert settings.snapshot()["revision"] == 1
    history = settings.history()
    assert history[0]["payload"]["old"] == 0.25
    assert history[0]["payload"]["reason"] == "measured tune"
    store.close()


def test_settings_reject_unknown_keys_types_and_out_of_range_values():
    store = FabricStore()
    settings = Settings(store)
    for key, value in [
        ("planner.feedback_scale", 0.51),
        ("planner.feedback_scale", "fast"),
        ("planner.cost_floor", True),
        ("auto_feedback.enabled", 1),
    ]:
        try:
            settings.set(key, value)
            raise AssertionError(f"{key}={value!r} was accepted")
        except ValueError:
            pass
    try:
        settings.set("validation.threshold", 0.0)
        raise AssertionError("unknown key was accepted")
    except KeyError:
        pass
    store.close()


def test_settings_reset_restores_defaults_and_keeps_history():
    store = FabricStore()
    settings = Settings(store)
    settings.set("feedback.prior", 9.0)
    result = settings.reset("feedback.prior", "rollback")
    assert result["changed"][0]["new"] == 5.0
    assert settings.get("feedback.prior") == 5.0
    assert len(settings.history()) == 2
    store.close()


def test_planner_can_disable_feedback_weighting():
    ops = [
        Operator("a1", frozenset({"text"}), frozenset({"a"})),
        Operator("a2", frozenset({"a"}), frozenset({"goal"})),
        Operator("b1", frozenset({"text"}), frozenset({"b"})),
        Operator("b2", frozenset({"b"}), frozenset({"goal"})),
    ]
    weights = {"a1": -1.0, "a2": -1.0, "b1": 1.0, "b2": 1.0}
    finder = PathFinder()
    weighted = finder.plan(("text",), "goal", ops, weights=weights)
    disabled = finder.plan(
        ("text",), "goal", ops, weights=weights, feedback_scale=0.0
    )
    assert [step.capability for step in weighted.steps] == ["b1", "b2"]
    assert [step.capability for step in disabled.steps] == ["a1", "a2"]


def test_auto_feedback_can_be_disabled():
    store = FabricStore()
    settings = Settings(store)
    settings.set("auto_feedback.enabled", False)
    engine = EvolutionEngine(
        store,
        guardians=GuardianRegistry([LocalGuardian()]),
        experts=[],
        settings=settings,
    )
    cycle = engine.evolve(
        "planning search text",
        goal_type="tokens",
        initial=("text",),
        text="alpha beta",
        sources=["local"],
        budget_s=5.0,
    )
    assert cycle.execution["ok"] is True
    assert feedback_scores(store).get("text.tokenize", 0.0) == 0.0
    store.close()


def test_tuning_uses_a_bounded_band_and_records_the_reason():
    store = FabricStore()
    settings = Settings(store)
    for _ in range(20):
        store.record_event("cycle", {"goal_type": "tokens", "ok": True})
    report = settings.tune()
    assert report["changed"] is True
    assert report["new"] == 0.3
    assert settings.get("planner.feedback_scale") == 0.3
    assert "skill" in report
    store.close()


def test_settings_endpoints_validate_and_return_history():
    client = TestClient(create_app())
    snapshot = client.get("/settings")
    assert snapshot.status_code == 200
    assert "planner.feedback_scale" in snapshot.json()["settings"]
    updated = client.post(
        "/settings",
        json={"key": "feedback.prior", "value": 7, "reason": "api test"},
    )
    assert updated.status_code == 200
    assert updated.json()["new"] == 7.0
    assert client.post(
        "/settings", json={"key": "feedback.prior", "value": 0}
    ).status_code == 400
    history = client.get("/settings/history").json()["events"]
    assert history[0]["payload"]["reason"] == "api test"
