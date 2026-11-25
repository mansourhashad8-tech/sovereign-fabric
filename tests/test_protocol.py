from sovereign.api import create_app
from sovereign.evolution import EvolutionEngine
from sovereign.guardians import GuardianRegistry, LocalGuardian
from sovereign.models import KnowledgeUnit, Provenance, utcnow
from sovereign.protocol import DeterministicProtocol, audit_language
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
