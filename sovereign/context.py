"""One context packet across knowledge, capabilities, events, graph, and settings.

This is a read-only join, not a hidden global workspace. Each section keeps its
own score and provenance; the packet says which retrieval mode produced it and
which limits apply.
"""

from __future__ import annotations

from typing import Any

from .feedback import feedback_scores
from .ranking import ranking_tokens
from .settings import Settings
from .vectors import cosine, embed

MAX_K = 20
MAX_EVENTS = 100
_STOP = {
    "the", "and", "for", "with", "into", "over", "from", "that", "this",
    "are", "was", "not", "a", "an", "it", "is", "of", "to", "in", "on",
    "by", "as", "or", "be", "at", "we", "you",
}


def _meaningful(text: str) -> set[str]:
    return {
        token
        for token in ranking_tokens(text)
        if len(token) > 2 and token not in _STOP
    }


class ContextFabric:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.store = engine.store
        self.settings = getattr(engine, "settings", Settings(engine.store))

    def build(self, query: str, k: int = 5) -> dict[str, Any]:
        query = str(query).strip()
        if not query:
            raise ValueError("query must not be empty")
        k = max(1, min(int(k), MAX_K))
        knowledge = self._knowledge(query, k)
        capabilities = self._capabilities(query, k)
        events = self._events(query, k)
        graph = self._graph(knowledge)
        links = self._links(knowledge, capabilities)
        return {
            "query": query,
            "knowledge": knowledge,
            "capabilities": capabilities,
            "events": events,
            "graph": graph,
            "links": links,
            "settings": {
                key: item["value"]
                for key, item in self.settings.snapshot()["settings"].items()
            },
            "limits": [
                "knowledge is ranked by hybrid vector/BM25 fusion, not a neural reader",
                "event relevance is token overlap over recent payloads, not causal attribution",
                "graph expansion is depth 1 and bounded",
                "links are shared-token candidates, not verified relationships",
                "settings are read-only here; use /settings to change them",
            ],
        }

    def _knowledge(self, query: str, k: int) -> list[dict[str, Any]]:
        hits = self.store.search_knowledge(query, k=k, mode="hybrid")
        return [
            {
                "id": unit.id,
                "title": unit.title,
                "summary": unit.summary,
                "concepts": list(unit.concepts),
                "tags": list(unit.tags),
                "source": unit.provenance.source,
                "url": unit.provenance.url,
                "score": round(score, 9),
            }
            for unit, score in hits
        ]

    def _capabilities(self, query: str, k: int) -> list[dict[str, Any]]:
        qvec = embed(query)
        feedback = feedback_scores(
            self.store, prior=float(self.settings.get("feedback.prior"))
        )
        rows = []
        for cap in self.engine.registry.list_active():
            text = " ".join([cap.name, cap.description, *cap.inputs, *cap.outputs])
            score = cosine(qvec, embed(text)) + 0.05 * feedback.get(cap.name, 0.0)
            rows.append(
                {
                    "name": cap.name,
                    "description": cap.description,
                    "inputs": list(cap.inputs),
                    "outputs": list(cap.outputs),
                    "score": round(score, 9),
                    "feedback": feedback.get(cap.name, 0.0),
                }
            )
        rows.sort(key=lambda item: (-item["score"], item["name"]))
        return rows[:k]

    def _events(self, query: str, k: int) -> list[dict[str, Any]]:
        wanted = set(ranking_tokens(query))
        scored = []
        for kind in ("cycle", "decision", "protocol"):
            for event in self.store.list_events(kind, MAX_EVENTS):
                payload = event.get("payload", {})
                text = " ".join(
                    str(payload.get(key, ""))
                    for key in ("request", "goal_type", "diagnosis", "kind")
                )
                overlap = len(wanted & set(ranking_tokens(text)))
                if overlap:
                    scored.append((overlap, event))
        scored.sort(key=lambda pair: (-pair[0], -pair[1]["id"]))
        return [
            {
                "id": event["id"],
                "kind": event["kind"],
                "ts": event["ts"],
                "payload": event["payload"],
                "score": overlap,
            }
            for overlap, event in scored[:k]
        ]

    def _graph(self, knowledge: list[dict[str, Any]]) -> dict[str, Any]:
        nodes: set[str] = set()
        edges: set[tuple[str, str, str]] = set()
        for item in knowledge:
            expansion = self.store.graph(item["id"], depth=1)
            nodes.update(str(node) for node in expansion["nodes"])
            edges.update(tuple(edge) for edge in expansion["edges"])
        return {
            "nodes": sorted(nodes)[:100],
            "edges": [list(edge) for edge in sorted(edges)[:200]],
            "truncated": len(nodes) > 100 or len(edges) > 200,
        }

    @staticmethod
    def _links(
        knowledge: list[dict[str, Any]], capabilities: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        links = []
        for unit in knowledge:
            unit_tokens = _meaningful(
                " ".join(
                    [unit["title"], unit["summary"], *unit.get("concepts", [])]
                )
            )
            for cap in capabilities:
                cap_tokens = _meaningful(
                    " ".join(
                        [cap["name"], cap["description"], *cap["inputs"], *cap["outputs"]]
                    )
                )
                shared = sorted(unit_tokens & cap_tokens)
                if shared:
                    links.append(
                        {
                            "knowledge": unit["id"],
                            "capability": cap["name"],
                            "shared": shared[:6],
                            "verified": False,
                        }
                    )
        return links[:40]
