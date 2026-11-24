"""Lexical claim support over the absorbed fabric.

This is deliberately not an entailment engine. It reports how much of a
claim's content vocabulary appears in retrieved units, and it says so.
"""

from __future__ import annotations

import re
from typing import Any

_WORD = re.compile(r"[A-Za-z0-9\u0600-\u06FF]{3,}")
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "are", "was",
    "were", "has", "have", "had", "not", "but", "can", "could", "should",
    "would", "does", "did", "how", "why", "what", "when", "where", "which",
    "who", "whom", "its", "their", "there", "then", "than", "them", "they",
    "you", "your", "our", "out", "about", "over", "under", "more", "most",
    "some", "such", "only", "also", "very", "just", "من", "في", "على", "إلى",
    "عن", "أن", "إن", "هذا", "هذه", "ذلك", "التي", "الذي", "هو", "هي", "مع",
    "كان", "كانت", "قد", "لا", "ما", "لم", "لن", "كل", "بعض", "أو", "ثم",
}


def content_terms(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.lower()) if word not in _STOP}


_terms = content_terms


def verify_claim(store, claim: str, k: int = 5, threshold: float = 0.5) -> dict[str, Any]:
    terms = _terms(claim)
    if not terms:
        return {
            "claim": claim,
            "supported": False,
            "entails": False,
            "kind": "lexical_support",
            "score": 0.0,
            "supporting": [],
            "reason": "the claim has no content words to check",
        }
    scored: list[dict[str, Any]] = []
    for unit, rank in store.search_knowledge(claim, k=k):
        overlap = len(terms & _terms(unit.searchable_text())) / len(terms)
        scored.append(
            {
                "title": unit.title,
                "source": unit.provenance.source,
                "url": unit.provenance.url,
                "overlap": round(overlap, 3),
                "rank": round(float(rank), 3),
            }
        )
    scored.sort(key=lambda item: (-item["overlap"], -item["rank"]))
    best = scored[0] if scored else None
    score = float(best["overlap"]) if best else 0.0
    supported = score >= threshold
    if supported:
        reason = (
            f"{sum(1 for item in scored if item['overlap'] >= threshold)} absorbed units "
            f"share at least {int(threshold * 100)}% of the claim's content words; "
            "this is lexical support, not entailment."
        )
    else:
        reason = "no absorbed unit shares enough content words; the claim is unsupported by the fabric"
    return {
        "claim": claim,
        "supported": supported,
        "entails": False,
        "kind": "lexical_support",
        "score": round(score, 3),
        "supporting": scored[:3],
        "reason": reason,
    }
