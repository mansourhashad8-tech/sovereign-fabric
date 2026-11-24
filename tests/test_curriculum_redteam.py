from sovereign.curriculum import Curriculum
from sovereign.evolution import EvolutionEngine
from sovereign.guardians import GuardianRegistry
from sovereign.models import KnowledgeUnit, Provenance, utcnow
from sovereign.redteam import OVERCLAIM_CORPUS, audit
from sovereign.store import FabricStore
from sovereign.validator import HolisticValidator


class ExtGuardian:
    def __init__(self, name):
        self.name = name

    def search(self, query, limit=5):
        return [
            KnowledgeUnit(
                id=f"{self.name}:1",
                title="Best first search",
                summary="graph search with a priority queue",
                provenance=Provenance(
                    source=self.name, url=f"https://{self.name}/1", retrieved_at=utcnow()
                ),
                concepts=("planning",),
            )
        ]


def test_curriculum_proposes_tasks_from_its_own_knowledge():
    store = FabricStore()
    for i in range(3):
        store.upsert_knowledge(
            KnowledgeUnit(
                id=f"k{i}",
                title=f"Topic {i}",
                summary=f"summary text {i}",
                provenance=Provenance(source="s", url=f"u{i}", retrieved_at=utcnow()),
            )
        )
    engine = EvolutionEngine(
        store, guardians=GuardianRegistry([ExtGuardian("alpha"), ExtGuardian("beta")])
    )
    curriculum = Curriculum(engine)
    tasks = curriculum.propose(2)
    assert [t.goal_type for t in tasks] == ["markdown", "upper"]
    results = curriculum.run(iterations=2, budget_s=5.0)
    assert len(results) == 2
    assert all(r["ok"] for r in results)
    assert results[1]["plan"] == ["text.upper"]
    store.close()


def test_redteam_corpus_is_fully_caught():
    report = audit(HolisticValidator())
    assert report["evaded"] == []
    assert report["coverage"] == 1.0
    assert len(report["caught"]) == len(OVERCLAIM_CORPUS)


def test_redteam_specific_phrases_are_flagged():
    validator = HolisticValidator()
    for phrase in (
        "1,000,000x faster",
        "orders of magnitude faster",
        "self-aware",
        "never wrong",
        "no limitations",
        "literally infinite",
    ):
        assert validator.detect_overclaims(phrase), phrase


def test_negated_claims_are_still_allowed():
    validator = HolisticValidator()
    assert validator.detect_overclaims("we do not claim quantum advantage") == []
