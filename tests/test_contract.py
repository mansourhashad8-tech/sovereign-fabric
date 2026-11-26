from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.contract import REQUIREMENTS, audit
from sovereign.evolution import EvolutionEngine
from sovereign.store import FabricStore


def test_contract_covers_functional_partial_and_literal_requirements():
    store = FabricStore()
    engine = EvolutionEngine(store, experts=[])
    try:
        report = audit(engine)
        assert report["coverage"]["total"] == len(REQUIREMENTS)
        assert report["coverage"]["met"] >= 10
        assert report["coverage"]["partial"] >= 1
        assert report["coverage"]["false"] >= 1
        ids = {item["id"] for item in report["gaps"]}
        assert {"digital_physical", "retrocausality", "absolute_unbounded"} <= ids
        assert report["live"]["capabilities"] > 0
        assert report["live"]["sources"] > 0
        assert report["note"].startswith("Curated from the conversation")
    finally:
        store.close()


def test_contract_endpoint_returns_the_same_ledger():
    client = TestClient(create_app())
    response = client.get("/contract")
    assert response.status_code == 200
    body = response.json()
    assert body["coverage"]["total"] == len(REQUIREMENTS)
    assert body["coverage"]["false"] >= 5
