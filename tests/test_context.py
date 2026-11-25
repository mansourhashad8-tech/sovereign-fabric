from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.context import ContextFabric
from sovereign.evolution import EvolutionEngine
from sovereign.guardians.sources import LocalGuardian
from sovereign.store import FabricStore


def _engine():
    store = FabricStore()
    engine = EvolutionEngine(store, experts=[])
    for unit in LocalGuardian().units:
        store.upsert_knowledge(unit)
    return store, engine


def test_context_joins_knowledge_capabilities_events_graph_and_settings():
    store, engine = _engine()
    try:
        packet = ContextFabric(engine).build("planning graph", k=5)
        assert packet["knowledge"] and packet["capabilities"]
        assert packet["settings"]["planner.feedback_scale"] == 0.25
        assert isinstance(packet["graph"]["nodes"], list)
        assert packet["links"] and all(link["verified"] is False for link in packet["links"])
        assert any("not a neural reader" in limit for limit in packet["limits"])
    finally:
        store.close()


def test_context_endpoint_rejects_blank_queries_and_serves_packets():
    client = TestClient(create_app())
    assert client.get("/context?q=").status_code == 422
    response = client.get("/context?q=search&k=3")
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "search"
    assert len(body["knowledge"]) <= 3
