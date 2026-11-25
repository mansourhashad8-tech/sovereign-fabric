import json

from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.autonomy import assess, reward_ledger
from sovereign.collective import (
    collective_status,
    export_bundle,
    import_bundle,
    lesson_from_event,
)
from sovereign.evolution import EvolutionEngine
from sovereign.immunity import ImmuneSystem
from sovereign.store import FabricStore


def test_immune_quarantines_a_scan_and_hashes_the_client():
    store = FabricStore()
    immune = ImmuneSystem(store, min_samples=3)
    for index in range(3):
        immune.observe("10.0.0.1", "/health", 200, 0.001, now=100 + index)
    assert immune.pre_check("10.0.0.1", "/health", now=110).allowed is True

    result = immune.observe(
        "10.0.0.1", "/.env?token=super-secret", 404, 0.001, now=111
    )
    assert result["quarantined"] is True
    assert result["suspicious"] is True
    assert immune.pre_check("10.0.0.1", "/health", now=112).allowed is False
    incident = immune.incidents()[0]["payload"]
    assert incident["category"] == "scan"
    assert incident["route_class"] == "/.env"
    assert "10.0.0.1" not in json.dumps(incident)
    assert "super-secret" not in json.dumps(incident)
    assert len(incident["client_hash"]) == 16
    immune.reset()
    assert immune.pre_check("10.0.0.1", "/health", now=113).allowed is True


def test_api_immune_quarantines_then_reset_unblocks():
    app = create_app()
    client = TestClient(app)
    assert client.get("/.env").status_code == 404
    blocked = client.get("/health")
    assert blocked.status_code == 403
    assert blocked.headers["retry-after"]
    assert client.post("/immunity/reset").status_code == 200
    assert client.get("/health").status_code == 200


def test_collective_export_is_anonymized_and_import_is_strict():
    store = FabricStore()
    immune = ImmuneSystem(store)
    immune.observe("192.0.2.9", "/.env?token=super-secret", 404, 0.001)
    bundle = export_bundle(store)
    assert bundle["count"] == 1
    assert bundle["federated_learning"] is False
    serialized = json.dumps(bundle)
    assert "192.0.2.9" not in serialized
    assert "super-secret" not in serialized
    lesson = bundle["lessons"][0]
    assert lesson["route_class"] == "/.env"
    assert lesson["fingerprint"]

    other = FabricStore()
    assert import_bundle(other, bundle)["accepted"] == 1
    assert import_bundle(other, bundle)["duplicates"] == 1
    assert collective_status(other)["lessons"] == 1

    tampered = json.loads(json.dumps(bundle))
    tampered["lessons"][0]["action"] = "pass"
    result = import_bundle(FabricStore(), tampered)
    assert result["ok"] is False
    assert result["rejected"][0]["reason"] == "fingerprint does not match the lesson"

    raw = json.loads(json.dumps(bundle))
    raw["lessons"][0]["client_ip"] = "192.0.2.9"
    result = import_bundle(FabricStore(), raw)
    assert result["ok"] is False
    assert "unknown fields" in result["rejected"][0]["reason"]


def test_autonomy_gate_requires_continuity_and_a_collective_lesson():
    store = FabricStore()
    engine = EvolutionEngine(store, experts=[])
    immune = ImmuneSystem(store)
    immune_status = immune.status()
    empty = collective_status(store)

    blocked = assess(
        engine,
        loop_status={"running": False, "generation": 0},
        immune_status=immune_status,
        collective=empty,
        include_security=False,
    )
    assert blocked["passed"] is False
    assert set(blocked["failed"]) == {"continuity", "collective"}

    store.record_event(
        "immune.incident",
        {
            "category": "scan",
            "route_class": "/.env",
            "score": 5.7,
            "action": "quarantine",
        },
    )
    passed = assess(
        engine,
        loop_status={"running": True, "generation": 1},
        immune_status=immune_status,
        collective=collective_status(store),
        include_security=False,
    )
    assert passed["passed"] is True
    assert passed["reward"]["mode"].startswith("transparent")
    assert reward_ledger(store)["components"]["immune_incidents"] == 1


def test_lesson_from_event_ignores_unrelated_events():
    assert lesson_from_event({"kind": "loop.tick", "payload": {}}) is None


def test_api_collective_and_autonomy_endpoints_are_wired():
    app = create_app()
    client = TestClient(app)
    assert client.get("/collective/status").json()["schema"] == "sovereign-collective/v1"
    bundle = client.get("/collective/export").json()
    assert bundle["federated_learning"] is False
    gate = client.get("/autonomy").json()
    assert gate["passed"] is False
    assert "continuity" in gate["failed"]
    assert "collective" in gate["failed"]
