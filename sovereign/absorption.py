"""Instant absorption: turn a consultation into indexed, linked knowledge.

Consulting is only useful if the result is immediately usable. absorb() does
the whole step in one pass: upsert the unit, index its embedding, and wire it
into the knowledge graph so it can be retrieved by meaning and traversed by
concept.
"""

from __future__ import annotations

import re

from .models import KnowledgeUnit
from .store import FabricStore

_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG.sub("-", text.strip().lower()).strip("-") or "item"


def absorb(store: FabricStore, units: list[KnowledgeUnit]) -> int:
    absorbed = 0
    for unit in units:
        store.upsert_knowledge(unit)
        for concept in unit.concepts:
            store.add_edge(unit.id, "has_concept", concept)
            store.add_edge(concept, "supported_by", unit.provenance.source)
        for tag in unit.tags:
            store.add_edge(unit.id, "tagged", tag)
        store.add_edge(unit.id, "from_source", unit.provenance.source)
        absorbed += 1
    if absorbed:
        store.record_event(
            "absorption",
            {"count": absorbed, "sources": sorted({u.provenance.source for u in units})},
        )
    return absorbed


def propose_capabilities(units: list[KnowledgeUnit]) -> list[dict[str, str]]:
    """Surface units that describe something executable (a package or repo).

    These are proposals only. Nothing is admitted without passing the
    synthesis verification gate.
    """
    proposals: list[dict[str, str]] = []
    for unit in units:
        tags = set(unit.tags)
        if "package" in tags or "code" in tags:
            proposals.append(
                {
                    "name": f"use.{_slug(unit.title)}",
                    "reason": f"{unit.provenance.source}: {unit.title}",
                    "source_url": unit.provenance.url,
                }
            )
    return proposals
