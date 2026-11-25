from sovereign.evolution import EvolutionEngine
from sovereign.guardians import GuardianRegistry, LocalGuardian
from sovereign.models import Evidence, KnowledgeUnit, Provenance, utcnow
from sovereign.store import FabricStore
from sovereign.validator import HolisticValidator

GOOD_CTX = {
    "sources_ok": 2,
    "sources_total": 2,
    "external_sources_ok": 2,
    "units_total": 2,
    "fresh_units": 2,
    "deterministic": True,
    "duration_s": 0.1,
    "budget_s": 5.0,
    "constraints_declared": 3,
    "constraints_addressed": 3,
}
EVIDENCE = [Evidence(kind="consultation", detail="2 units", ref="alpha,beta")]
CLAIMS = ["produced a markdown artifact"]


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
                    source=self.name, url=f"https://{self.name}/1", retrieved_at=utcnow()
                ),
                concepts=("planning", "search"),
                tags=("paper",),
            )
        ]


def _fake_registry() -> GuardianRegistry:
    return GuardianRegistry([FakeGuardian("alpha"), FakeGuardian("beta"), LocalGuardian()])


UPPER_SYNTH = {
    "name": "text.upper",
    "description": "uppercase",
    "inputs": ("text",),
    "outputs": ("upper",),
    "spec": {"op": "upper"},
    "examples": [({"value": "abc"}, {"value": "ABC"})],
}


# -- validator ---------------------------------------------------------------
def test_validator_passes_with_full_evidence():
    report = HolisticValidator().validate("subject", CLAIMS, EVIDENCE, GOOD_CTX)
    assert report.passed is True
    assert report.failures == []
    assert all(score >= 0.5 for score in report.scores.values())


def test_validator_fails_without_evidence():
    report = HolisticValidator().validate("subject", CLAIMS, [], GOOD_CTX)
    assert report.passed is False
    assert any("no evidence" in f for f in report.failures)


def test_validator_flags_unmeasured_speed():
    ctx = dict(GOOD_CTX)
    ctx.pop("duration_s")
    report = HolisticValidator().validate("subject", CLAIMS, EVIDENCE, ctx)
    assert report.scores["speed"] == 0.0
    assert report.passed is False


def test_validator_requires_external_guardianship():
    ctx = dict(GOOD_CTX, external_sources_ok=0)
    report = HolisticValidator().validate("subject", CLAIMS, EVIDENCE, ctx)
    assert report.scores["guardianship"] == 0.0
    assert report.passed is False


def test_overclaim_detection():
    v = HolisticValidator()
    assert v.detect_overclaims("we achieved a million times speedup")
    assert v.detect_overclaims("guaranteed, no failures ever")
    assert v.detect_overclaims("this is impossible")


def test_overclaim_detection_respects_negation():
    v = HolisticValidator()
    assert v.detect_overclaims("we do not claim quantum advantage") == []
    assert v.detect_overclaims("it is not impossible") == []
    assert v.detect_overclaims("the volcano model") == []


def test_overclaim_fails_even_with_evidence():
    report = HolisticValidator().validate(
        "deliver a million-fold speedup", CLAIMS, EVIDENCE, GOOD_CTX
    )
    assert report.overclaims
    assert report.passed is False


# -- evolution ---------------------------------------------------------------
def test_cycle_succeeds_with_external_guardianship():
    store = FabricStore()
    engine = EvolutionEngine(store, guardians=_fake_registry())
    cycle = engine.evolve("planning search text", text="alpha beta alpha", budget_s=5.0)
    assert cycle.plan.solved is True
    assert cycle.execution["ok"] is True
    assert cycle.validation.passed is True
    assert cycle.ok is True
    assert cycle.execution["value"]  # produced markdown
    assert store.list_events("cycle")
    store.close()


def test_cycle_with_only_local_knowledge_refuses_to_claim_success():
    store = FabricStore()
    engine = EvolutionEngine(store)
    cycle = engine.evolve("planning search text", text="a b a", sources=["local"], budget_s=5.0)
    assert cycle.plan.solved is True
    assert cycle.execution["ok"] is True
    assert cycle.validation.scores["guardianship"] == 0.0
    assert cycle.validation.passed is False
    assert cycle.ok is False
    store.close()


def test_cycle_rejects_overclaiming_request():
    store = FabricStore()
    engine = EvolutionEngine(store, guardians=_fake_registry())
    cycle = engine.evolve(
        "give me a million-fold speedup", text="a b", budget_s=5.0
    )
    assert cycle.validation.overclaims
    assert cycle.ok is False
    store.close()


def test_cycle_synthesizes_missing_capability_then_succeeds():
    store = FabricStore()
    engine = EvolutionEngine(store, guardians=_fake_registry())
    cycle = engine.evolve(
        "uppercase the planning text",
        goal_type="upper",
        initial=("text",),
        text="abc",
        synthesize=UPPER_SYNTH,
        budget_s=5.0,
    )
    assert cycle.synthesis is not None and cycle.synthesis.admitted is True
    assert cycle.plan.solved is True
    assert cycle.execution["value"] == "ABC"
    assert cycle.ok is True
    store.close()


def test_cycle_records_failure_memo_for_unreachable_goal():
    store = FabricStore()
    engine = EvolutionEngine(store, guardians=_fake_registry())
    cycle = engine.evolve("planning text", goal_type="teleport", text="x", budget_s=5.0)
    assert cycle.plan.solved is False
    assert cycle.ok is False
    assert store.memo_entries()
    store.close()


def test_robust_evolve_records_every_attempt():
    store = FabricStore()
    engine = EvolutionEngine(store)
    cycle = engine.evolve(
        "planning search text", text="a b a", sources=["local"],
        budget_s=5.0, max_attempts=3,
    )
    assert len(cycle.attempts) == 3
    assert cycle.ok is False
    assert cycle.diagnosis
    assert any("external" in d for d in cycle.diagnosis)
    store.close()


def test_auto_extend_solves_a_goal_it_could_not_plan():
    store = FabricStore()
    engine = EvolutionEngine(store, guardians=_fake_registry())
    cycle = engine.evolve(
        "planning text", goal_type="doubled", initial=("text",), text="ab",
        auto_extend=True, budget_s=5.0,
    )
    assert cycle.plan.solved is True
    assert [s.capability for s in cycle.plan.steps] == ["text.double"]
    assert cycle.execution["value"] == "abab"
    assert cycle.extensions and cycle.extensions[0]["admitted"] is True
    assert cycle.ok is True
    store.close()


def test_self_calibration_is_prequential_and_honest():
    from sovereign.selfmodel import SelfModel

    store = FabricStore()
    engine = EvolutionEngine(
        store, guardians=GuardianRegistry([LocalGuardian()]), experts=[]
    )
    for ok in (True, True, False):
        engine.store.record_event(
            "cycle", {"goal_type": "tokens", "ok": ok, "duration_s": 0.01}
        )
    report = SelfModel(engine).calibration()
    assert report["cycles"] == 3
    assert report["rows"][0]["predicted"] == 0.5
    assert report["rows"][1]["predicted"] > report["rows"][0]["predicted"]
    assert "diagnostic" in report["note"]
    store.close()
