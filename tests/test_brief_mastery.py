from sovereign.brief import build_brief
from sovereign.evolution import EvolutionEngine
from sovereign.guardians import GuardianRegistry, LocalGuardian
from sovereign.mastery import Mastery
from sovereign.store import FabricStore


def _engine():
    store = FabricStore()
    engine = EvolutionEngine(store, guardians=GuardianRegistry([LocalGuardian()]), experts=[])
    return store, engine


def test_brief_is_cited_extractive_and_absorbs():
    store, engine = _engine()
    result = build_brief(engine, "planning and search", limit=3, sources=["local"])
    assert result["ok"] is True
    assert result["units"]
    assert result["absorbed"] > 0
    assert "## What the sources say" in result["markdown"]
    assert "does not infer" in result["markdown"]
    assert result["coverage"] > 0
    store.close()


def test_arabic_brief_uses_arabic_headings():
    store, engine = _engine()
    result = build_brief(engine, "planning and search", limit=2, sources=["local"], lang="ar")
    assert "موجز بحثي" in result["markdown"]
    assert "ما تقوله المصادر" in result["markdown"]
    assert "لم يُحاول" in result["markdown"]
    store.close()


def test_empty_brief_is_honest():
    class Boom:
        name = "boom"

        def search(self, query, limit=5):
            raise RuntimeError("down")

    store = FabricStore()
    engine = EvolutionEngine(store, guardians=GuardianRegistry([Boom()]), experts=[])
    result = build_brief(engine, "anything", limit=3)
    assert result["ok"] is False
    assert result["units"] == []
    assert any("did not answer" in gap for gap in result["gaps"])
    assert "No units were returned" in result["markdown"]
    store.close()


def test_mastery_tracks_and_practises_the_weakest_goal():
    store, engine = _engine()
    engine.evolve("planning and search", goal_type="markdown", sources=["local"], budget_s=5)
    model = Mastery(engine)
    before = model.table()
    assert before["markdown"]["attempts"] >= 1
    result = model.practice(iterations=1, sources=["local"], budget_s=5)
    assert result["weakest_before"] in before
    assert result["after"]["markdown"]["attempts"] > before["markdown"]["attempts"]
    store.close()
