from sovereign.api import create_app
from sovereign.evolution import EvolutionEngine
from sovereign.guardians import GuardianRegistry, LocalGuardian
from sovereign.models import KnowledgeUnit, Provenance, utcnow
from sovereign.protocol import DeterministicProtocol, audit_language
from sovereign.gaps import gap_summary, protocol_history
from sovereign.decisions import decision_summary, lookup_decisions
from sovereign.store import FabricStore
from fastapi.testclient import TestClient


class FakeGuardian:
    def __init__(self, name: str) -> None:
        self.name = name

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:
        return [
            KnowledgeUnit(
                id=f"{self.name}:1",
                title=f"{self.name} planning result",
                summary="fresh relevant knowledge about planning and search",
                provenance=Provenance(
                    source=self.name,
                    url=f"https://{self.name}/1",
                    retrieved_at=utcnow(),
                ),
                concepts=("planning", "search"),
                tags=("paper",),
            )
        ]


def _verified_engine() -> EvolutionEngine:
    return EvolutionEngine(
        FabricStore(),
        guardians=GuardianRegistry(
            [FakeGuardian("alpha"), FakeGuardian("beta"), LocalGuardian()]
        ),
        experts=[],
    )


def test_language_audit_flags_banned_phrases_and_accepts_solution_language():
    assert audit_language("هذا مستحيل") .compliant is False
    assert audit_language("تم تحقيق النتيجة بالدليل") .compliant is True


def test_decision_memory_records_the_route_and_reuses_only_by_exact_hash():
    engine = _verified_engine()
    try:
        report = DeterministicProtocol(engine).execute(
            "planning search text", text="alpha beta alpha", budget_s=5.0
        )
        assert report["decision_id"]
        summary = decision_summary(engine.store)
        assert summary["decisions"] == 1
        assert summary["verified"] == 1
        assert summary["recent"][0]["route"] == "direct"
        found = lookup_decisions(engine.store, report["request_hash"])
        assert found["count"] == 1
        assert found["decisions"][0]["payload"]["automatic_reuse"] is False
        assert "planning search text" not in str(summary)
        assert "planning search text" not in str(found)
    finally:
        engine.store.close()


def test_protocol_routes_include_a_real_broader_query_and_all_sources_retry():
    engine = _verified_engine()
    try:
        routes = DeterministicProtocol(engine).routes(
            "markdown", ("text",), None, ["local"]
        )
        names = [route.name for route in routes]
        assert names[:3] == ["direct", "broader_retrieval", "all_sources_retry"]
        assert routes[1].query_suffix
        assert routes[2].all_sources is True
    finally:
        engine.store.close()


def test_protocol_returns_verified_only_when_the_validator_passes():
    engine = _verified_engine()
    report = DeterministicProtocol(engine).execute(
        "planning search text", text="alpha beta alpha", budget_s=5.0
    )
    assert report["status"] == "verified"
    assert report["verified"] is True
    assert report["result"]
    assert report["final_validation"]["exact_match"] is True
    assert report["alternatives"][0]["name"] == "direct"
    assert report["language_audit"]["compliant"] is True
    engine.store.close()


def test_protocol_escalates_with_the_exact_gap_and_next_actions():
    engine = EvolutionEngine(
        FabricStore(), guardians=GuardianRegistry([LocalGuardian()]), experts=[]
    )
    report = DeterministicProtocol(engine).execute(
        "planning search text",
        text="a b a",
        sources=["local"],
        budget_s=1.0,
        max_alternatives=2,
    )
    assert report["status"] == "escalation_required"
    assert report["verified"] is False
    assert report["result"] is None
    assert report["next_actions"]
    assert any("external source" in action for action in report["next_actions"])
    assert report["language_audit"]["compliant"] is True
    engine.store.close()


def test_protocol_records_a_gap_without_storing_the_raw_request():
    engine = EvolutionEngine(
        FabricStore(), guardians=GuardianRegistry([LocalGuardian()]), experts=[]
    )
    try:
        report = DeterministicProtocol(engine).execute(
            "private planning request",
            text="a b a",
            sources=["local"],
            budget_s=1.0,
            max_alternatives=2,
        )
        assert report["recorded"] is True
        assert report["request_hash"]
        summary = gap_summary(engine.store)
        assert summary["runs"] == 1
        assert summary["escalated"] == 1
        assert summary["verified"] == 0
        assert summary["recent"][0]["request_hash"] == report["request_hash"]
        assert summary["proposed_capabilities"]
        assert all(item["auto_created"] is False for item in summary["proposed_capabilities"])
        assert "private planning request" not in str(summary)
        history = protocol_history(engine.store)
        assert history["runs"][0]["payload"]["status"] == "escalation_required"
        assert "private planning request" not in str(history)
    finally:
        engine.store.close()


def test_protocol_api_exposes_status_execution_and_language_audit():
    app = create_app()
    client = TestClient(app)
    assert client.get("/protocol").json()["protocol"] == "sovereign-deterministic/v1"
    audit = client.post("/protocol/language", json={"text": "هذا مستحيل"}).json()
    assert audit["compliant"] is False
    result = client.post(
        "/protocol/execute",
        json={
            "request": "planning search text",
            "text": "a b a",
            "sources": ["local"],
            "budget_s": 1.0,
            "max_alternatives": 2,
        },
    ).json()
    assert result["status"] == "escalation_required"
    assert result["next_actions"]
    assert client.get("/gaps").json()["escalated"] >= 1
    assert client.get("/protocol/history").json()["runs"]
    assert client.get("/decisions").json()["decisions"] >= 1
    assert client.get(f"/decisions/{result['request_hash']}").json()["count"] >= 1
