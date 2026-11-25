"""A small, fixed retrieval benchmark over the offline local corpus.

This is a controlled regression check, not a public leaderboard. It exists so
the three retrieval modes can be compared on the same ten queries and the
result can be reproduced without a network.
"""

from __future__ import annotations

from typing import Any

from .guardians.sources import LocalGuardian
from .ranking import evaluate_ranking
from .store import FabricStore

QUERIES: tuple[dict[str, Any], ...] = (
    {
        "query": "search",
        "relevance": {
            "local:best-first-search": 2.0,
            "local:planning-as-graph-search": 1.0,
            "local:failure-memo": 1.0,
        },
    },
    {
        "query": "storage",
        "relevance": {"local:sqlite-wal": 2.0, "local:provenance": 1.0},
    },
    {
        "query": "vector",
        "relevance": {"local:hashing-trick": 2.0, "local:openalex": 1.0},
    },
    {
        "query": "planning",
        "relevance": {
            "local:planning-as-graph-search": 2.0,
            "local:best-first-search": 1.0,
        },
    },
    {
        "query": "model",
        "relevance": {
            "local:quantum-simulator-limits": 2.0,
            "local:hashing-trick": 1.0,
            "local:openalex": 1.0,
        },
    },
    {
        "query": "data audit",
        "relevance": {"local:provenance": 2.0, "local:sqlite-wal": 1.0},
    },
    {
        "query": "version",
        "relevance": {
            "local:capability-registry": 2.0,
            "local:failure-memo": 1.0,
        },
    },
    {
        "query": "isolation",
        "relevance": {"local:subprocess-sandbox": 2.0},
    },
    {
        "query": "rate api",
        "relevance": {"local:rate-limiting": 2.0, "local:openalex": 1.0},
    },
    {
        "query": "abstract",
        "relevance": {"local:openalex": 2.0, "local:hashing-trick": 1.0},
    },
    {
        "query": "pruning",
        "relevance": {"local:failure-memo": 2.0, "local:best-first-search": 1.0},
    },
    {
        "query": "quantum",
        "relevance": {"local:quantum-simulator-limits": 2.0},
    },
)


def run_benchmark(k: int = 5) -> dict[str, Any]:
    k = max(1, min(int(k), 12))
    store = FabricStore()
    try:
        for unit in LocalGuardian().units:
            store.upsert_knowledge(unit)
        modes: dict[str, Any] = {}
        for mode in ("vector", "bm25", "hybrid"):
            rows = []
            for item in QUERIES:
                hits = store.search_knowledge(item["query"], k=k, mode=mode)
                ranked = [unit.id for unit, _ in hits]
                metrics = evaluate_ranking(ranked, item["relevance"], k=k)
                rows.append(
                    {
                        "query": item["query"],
                        "relevance": item["relevance"],
                        "ranked": ranked,
                        **metrics,
                    }
                )
            modes[mode] = {
                "ndcg": round(sum(row["ndcg"] for row in rows) / len(rows), 6),
                "mrr": round(sum(row["mrr"] for row in rows) / len(rows), 6),
                "rows": rows,
            }
        best = max(modes, key=lambda name: (modes[name]["ndcg"], modes[name]["mrr"]))
        return {
            "k": k,
            "corpus_size": len(LocalGuardian().units),
            "queries": len(QUERIES),
            "modes": modes,
            "best_mode": best,
            "note": (
                "fixed internal benchmark over the offline local corpus; "
                "it is not a public leaderboard and does not prove general superiority"
            ),
        }
    finally:
        store.close()
