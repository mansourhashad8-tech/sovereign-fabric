import pytest
from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.models import KnowledgeUnit, Provenance, utcnow
from sovereign.ranking import (
    bm25_scores,
    evaluate_ranking,
    mrr,
    ndcg_at_k,
    ranking_tokens,
    reciprocal_rank_fusion,
)
from sovereign.store import FabricStore


def _unit(uid, title, summary):
    return KnowledgeUnit(
        id=uid,
        title=title,
        summary=summary,
        provenance=Provenance(source="test", url=f"test://{uid}", retrieved_at=utcnow()),
    )


def test_bm25_rewards_a_rare_exact_term():
    scores = bm25_scores(
        "sqlite",
        [
            "planning search over state spaces",
            "SQLite write-ahead logging",
            "planning with a heuristic",
        ],
    )
    assert scores[1] > scores[0]
    assert scores[1] > scores[2]


def test_bm25_handles_empty_queries_and_documents():
    assert bm25_scores("", ["anything"]) == [0.0]
    assert bm25_scores("anything", []) == []


def test_reciprocal_rank_fusion_combines_two_rankings():
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]])
    assert fused["b"] > fused["a"]
    assert fused["b"] > fused["c"]


def test_ranking_tokens_normalize_arabic_and_case():
    assert ranking_tokens("الذكاءُ الاصطناعي") == ["الذكاء", "الاصطناعي"]
    assert ranking_tokens("SQLite WAL") == ["sqlite", "wal"]


def test_store_supports_vector_bm25_and_hybrid_modes():
    store = FabricStore()
    store.upsert_knowledge(_unit("rare", "SQLite WAL", "write-ahead logging"))
    store.upsert_knowledge(_unit("common", "Planning", "search and heuristics"))
    bm25 = store.search_knowledge("sqlite", k=2, mode="bm25")
    assert bm25[0][0].id == "rare"
    assert bm25[0][1] > bm25[1][1]
    hybrid = store.search_knowledge("sqlite", k=2, mode="hybrid")
    assert hybrid[0][0].id == "rare"
    assert hybrid[0][1] > 0
    with pytest.raises(ValueError):
        store.search_knowledge("sqlite", mode="not-a-mode")
    store.close()


def test_knowledge_search_api_exposes_mode_and_rejects_unknown_mode():
    client = TestClient(create_app())
    ok = client.get("/knowledge/search", params={"q": "planning", "mode": "bm25"})
    assert ok.status_code == 200
    assert ok.json()["mode"] == "bm25"
    bad = client.get("/knowledge/search", params={"q": "planning", "mode": "bogus"})
    assert bad.status_code == 422


def test_ndcg_and_mrr_reward_early_relevant_items():
    relevance = {"a": 2.0, "b": 1.0}
    assert ndcg_at_k(["a", "x", "b"], relevance, k=3) > ndcg_at_k(["x", "b", "a"], relevance, k=3)
    assert ndcg_at_k(["a", "b"], relevance, k=2) == 1.0
    assert mrr(["x", "b", "a"], {"a", "b"}) == 0.5
    assert mrr(["x"], {"a"}) == 0.0


def test_evaluate_ranking_returns_ndcg_mrr_and_k():
    result = evaluate_ranking(["a", "b"], {"a": 1.0}, k=2)
    assert result == {"ndcg": 1.0, "mrr": 1.0, "k": 2}


def test_ranking_evaluation_api():
    client = TestClient(create_app())
    response = client.post(
        "/ranking/evaluate",
        json={"ranked": ["a", "b"], "relevance": {"a": 1.0}, "k": 2},
    )
    assert response.status_code == 200
    assert response.json()["ndcg"] == 1.0


def test_fixed_retrieval_benchmark_is_reproducible_and_bounded():
    client = TestClient(create_app())
    response = client.get("/ranking/benchmark", params={"k": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["queries"] == 12
    assert set(body["modes"]) == {"vector", "bm25", "hybrid"}
    assert all(0.0 <= body["modes"][mode]["ndcg"] <= 1.0 for mode in body["modes"])
    assert body["best_mode"] in body["modes"]


def test_bm25_index_is_cached_and_invalidated_on_write():
    store = FabricStore()
    try:
        store.upsert_knowledge(_unit("a", "SQLite", "write-ahead logging"))
        store.search_knowledge("sqlite", mode="bm25")
        first = store.retrieval_index_status()
        assert first["cached"] is True
        assert first["documents"] == 1
        store.upsert_knowledge(_unit("b", "Planning", "state space search"))
        assert store.retrieval_index_status()["cached"] is False
        store.search_knowledge("planning", mode="hybrid")
        second = store.retrieval_index_status()
        assert second["cached"] is True
        assert second["documents"] == 2
    finally:
        store.close()
