from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.capabilities import CapabilityRegistry, bootstrap_native
from sovereign.evolution import EvolutionEngine
from sovereign.feedback import record_feedback
from sovereign.guardians import GuardianRegistry, LocalGuardian
from sovereign.repair import repair
from sovereign.store import FabricStore


def _engine(store=None):
    store = store or FabricStore()
    return EvolutionEngine(
        store, guardians=GuardianRegistry([LocalGuardian()]), experts=[]
    )


def test_feedback_changes_search_ranking_and_summary():
    client = TestClient(create_app())
    first = client.post(
        "/feedback",
        json={"capability": "math.eval", "rating": 1, "note": "useful"},
    )
    assert first.status_code == 200
    assert first.json()["feedback"]["rating"] == 1

    rows = client.get("/feedback/summary").json()["rows"]
    row = next(item for item in rows if item["capability"] == "math.eval")
    assert row["count"] == 1
    assert row["positive"] == 1
    assert row["score"] > 0

    hits = client.get("/capabilities/search?q=arithmetic&k=3").json()["hits"]
    assert any(hit["name"] == "math.eval" and hit["feedback"] > 0 for hit in hits)
    assert client.post(
        "/feedback", json={"capability": "math.eval", "rating": 2}
    ).status_code == 422


def test_feedback_rejects_bad_rating_directly():
    store = FabricStore()
    try:
        record_feedback(store, "math.eval", 2)
        raise AssertionError("bad rating was accepted")
    except ValueError as exc:
        assert "rating" in str(exc)
    finally:
        store.close()


def test_repair_quarantines_a_broken_entry_and_restores_it():
    engine = _engine()
    broken = engine.registry.active("math.eval")
    broken.entry = "sovereign.extras:missing"
    engine.store.save_capability(broken)

    result = repair(engine)
    actions = {(item["action"], item["capability"]) for item in result["actions"]}
    assert ("quarantined", "math.eval") in actions
    assert ("restored", "math.eval") in actions
    assert result["ok"] is True
    assert result["remaining_issues"] == []
    assert engine.registry.invoke("math.eval", {"value": "2+3"})["value"] == 5
    engine.store.close()


def test_repair_endpoint_is_safe_on_a_clean_engine():
    client = TestClient(create_app())
    body = client.post("/self/repair").json()
    assert body["ok"] is True
    assert body["actions"] == []
    assert body["remaining_issues"] == []


def test_native_bootstrap_restores_only_missing_names():
    store = FabricStore()
    registry = CapabilityRegistry(store)
    bootstrap_native(registry)
    version = registry.active("text.tokenize").version
    bootstrap_native(registry)
    assert registry.active("text.tokenize").version == version
    store.close()
