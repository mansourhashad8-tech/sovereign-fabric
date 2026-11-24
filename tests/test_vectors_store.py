import os

from sovereign.models import Capability, KnowledgeUnit, Provenance, utcnow
from sovereign.store import FabricStore
from sovereign.vectors import DEFAULT_DIM, cosine, embed, tokenize


def _unit(uid: str, title: str, summary: str, source: str = "local") -> KnowledgeUnit:
    return KnowledgeUnit(
        id=uid,
        title=title,
        summary=summary,
        provenance=Provenance(source=source, url=f"local://{uid}"),
        concepts=("planning",),
        tags=("algorithm",),
    )


def test_embed_is_deterministic_and_normalized():
    a = embed("best first search planning")
    b = embed("best first search planning")
    assert a == b
    assert len(a) == DEFAULT_DIM
    norm = sum(x * x for x in a) ** 0.5
    assert abs(norm - 1.0) < 1e-9
    assert cosine(a, a) > 0.999


def test_tokenize_lowercases_and_splits():
    assert tokenize("Hello, World 42") == ["hello", "world", "42"]


def test_store_roundtrip_and_search():
    store = FabricStore()
    store.upsert_knowledge(_unit("a", "Best first search", "graph search with a priority queue"))
    store.upsert_knowledge(_unit("b", "SQLite WAL", "write ahead logging for concurrency"))
    assert store.count_knowledge() == 2

    fetched = store.get_knowledge("a")
    assert fetched is not None and fetched.title == "Best first search"
    assert len(fetched.embedding) == DEFAULT_DIM

    hits = store.search_knowledge("priority queue search", k=2)
    assert hits[0][0].id == "a"
    assert hits[0][1] > hits[1][1]
    store.close()


def test_store_edges_and_neighbors():
    store = FabricStore()
    store.add_edge("unit:a", "has_concept", "planning")
    store.add_edge("unit:a", "from_source", "local")
    edges = store.neighbors("unit:a")
    assert ("unit:a", "has_concept", "planning") in edges
    only = store.neighbors("unit:a", rel="from_source")
    assert only == [("unit:a", "from_source", "local")]
    store.close()


def test_capability_versioning_and_status():
    store = FabricStore()
    cap = Capability(name="x.op", description="d", inputs=("a",), outputs=("b",))
    store.save_capability(cap)
    assert store.next_version("x.op") == 2
    cap2 = Capability(name="x.op", description="d2", inputs=("a",), outputs=("b",), version=2)
    store.save_capability(cap2)
    latest = store.get_capability("x.op")
    assert latest is not None and latest.version == 2
    assert store.get_capability("x.op", 1).description == "d"
    assert store.set_capability_status("x.op", 2, "rolled_back") is True
    assert store.get_capability("x.op", 2).status == "rolled_back"
    store.close()


def test_events_cache_and_memo():
    store = FabricStore()
    store.record_event("demo", {"k": 1})
    events = store.list_events("demo")
    assert events[0]["payload"] == {"k": 1}

    store.cache_set("k", {"v": 1})
    assert store.cache_get("k", ttl=3600) == {"v": 1}
    assert store.cache_get("k", ttl=-1) is None

    assert store.memo_seen("sig") is False
    store.memo_record("sig", "dead end")
    assert store.memo_seen("sig") is True
    entries = store.memo_entries()
    assert entries[0]["sig"] == "sig" and entries[0]["count"] == 1
    store.close()


def test_persistence_to_file(tmp_path):
    path = os.path.join(tmp_path, "fabric.db")
    store = FabricStore(path)
    store.upsert_knowledge(_unit("persist", "Persisted", "durable across reopen"))
    store.close()

    reopened = FabricStore(path)
    assert reopened.count_knowledge() == 1
    assert reopened.get_knowledge("persist").title == "Persisted"
    reopened.close()


def test_utcnow_is_isoformat():
    stamp = utcnow()
    assert "T" in stamp


def test_hybrid_search_prefers_recent_on_ties():
    store = FabricStore()
    old = KnowledgeUnit(
        id="old", title="Same title", summary="same words here",
        provenance=Provenance(source="s", url="u1", retrieved_at="2015-01-01T00:00:00+00:00"),
    )
    new = KnowledgeUnit(
        id="new", title="Same title", summary="same words here",
        provenance=Provenance(source="s", url="u2", retrieved_at=utcnow()),
    )
    store.upsert_knowledge(old)
    store.upsert_knowledge(new)
    hits = store.search_knowledge("same words here", k=2)
    assert hits[0][0].id == "new"
    store.close()


def test_graph_traversal_depth_two():
    store = FabricStore()
    store.add_edge("a", "to", "b")
    store.add_edge("b", "to", "c")
    g = store.graph("a", depth=2)
    assert {"a", "b", "c"} <= set(g["nodes"])
    assert ["a", "to", "b"] in g["edges"]
    assert ["b", "to", "c"] in g["edges"]
    store.close()
