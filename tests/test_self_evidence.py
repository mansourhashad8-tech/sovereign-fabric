from sovereign.evidence import verify_claim
from sovereign.evolution import EvolutionEngine
from sovereign.guardians import GuardianRegistry, LocalGuardian
from sovereign.models import KnowledgeUnit, Provenance
from sovereign.selfmodel import SelfModel
from sovereign.store import FabricStore


def _unit(store):
    store.upsert_knowledge(
        KnowledgeUnit(
            id="rag-1",
            title="Retrieval augmented generation",
            summary="RAG improves factuality by grounding answers in retrieved documents.",
            provenance=Provenance(
                source="local", url="https://example.org/rag", license="test", confidence=0.9
            ),
        )
    )


def test_self_model_plans_real_goals_and_refuses_unknown_ones():
    store = FabricStore()
    engine = EvolutionEngine(store, guardians=GuardianRegistry([LocalGuardian()]), experts=[])
    model = SelfModel(engine)
    assert model.can("markdown")["possible"] is True
    assert model.can("summary")["plan"] == ["text.summarize"]
    assert model.can("no.such.goal")["possible"] is False
    store.close()


def test_self_model_states_limits_and_passes_its_own_audit():
    store = FabricStore()
    engine = EvolutionEngine(store, guardians=GuardianRegistry([LocalGuardian()]), experts=[])
    result = SelfModel(engine).assess()
    assert result["overclaims"] == []
    assert any("No external model expert" in limit for limit in result["limits"])
    assert "not conscious" in result["verdict"]
    store.close()


def test_claim_is_supported_by_absorbed_text():
    store = FabricStore()
    _unit(store)
    result = verify_claim(store, "retrieval augmented generation improves factuality")
    assert result["supported"] is True
    assert result["entails"] is False
    assert result["score"] >= 0.5
    assert result["supporting"][0]["source"] == "local"
    store.close()


def test_unrelated_claim_is_refused():
    store = FabricStore()
    _unit(store)
    result = verify_claim(store, "the moon is made of cheese")
    assert result["supported"] is False
    assert "unsupported" in result["reason"]
    store.close()
