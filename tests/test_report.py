from sovereign.evolution import EvolutionEngine
from sovereign.guardians import GuardianRegistry, LocalGuardian
from sovereign.models import KnowledgeUnit, Provenance, utcnow
from sovereign.report import render_report, system_report
from sovereign.store import FabricStore


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


def _engine():
    store = FabricStore()
    registry = GuardianRegistry([LocalGuardian(), ExtGuardian("alpha"), ExtGuardian("beta")])
    return store, EvolutionEngine(store, guardians=registry)


def test_report_completes_with_external_sources():
    store, engine = _engine()
    report = system_report(
        engine,
        query="planning search",
        sources=["local", "alpha", "beta"],
        budget_s=5.0,
        benchmark_n=10,
        iterations=1000,
        benchmark_mode="serial",
    )
    assert report["ok"] is True
    assert report["cycle"]["validation"]["passed"] is True
    assert report["guardians"]["ok_sources"] == 3
    assert report["redteam"]["coverage"] == 1.0
    assert report["honesty"]["overclaims"] == []
    store.close()


def test_report_is_honest_when_only_local():
    store, engine = _engine()
    report = system_report(
        engine,
        query="planning",
        sources=["local"],
        budget_s=3.0,
        benchmark_n=5,
        iterations=500,
        benchmark_mode="serial",
    )
    assert report["ok"] is False
    assert "not validated" in report["verdict"] or "not completed" in report["verdict"]
    store.close()


def test_rendered_report_passes_its_own_audit():
    store, engine = _engine()
    report = system_report(
        engine,
        query="planning search",
        sources=["local", "alpha", "beta"],
        budget_s=5.0,
        benchmark_n=5,
        iterations=500,
        benchmark_mode="serial",
    )
    text = render_report(report)
    assert "Verdict" in text
    assert "Measured" in text
    assert engine.validator.detect_overclaims(text) == []
    store.close()
