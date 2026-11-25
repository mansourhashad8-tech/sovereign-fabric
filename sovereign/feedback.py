"""Outcome feedback that nudges capability ranking, not a trained model.

A rating is -1, 0, or +1. The score is smoothed by a prior so one rating does
not dominate a capability with a long history. It is deliberately simple and
fully inspectable.
"""

from __future__ import annotations

from typing import Any

from .store import FabricStore

PRIOR = 5.0
MAX_EVENTS = 5_000


def record_feedback(
    store: FabricStore,
    capability: str,
    rating: int,
    note: str = "",
    request_id: str | None = None,
) -> dict[str, Any]:
    if rating not in {-1, 0, 1}:
        raise ValueError("rating must be -1, 0, or 1")
    payload = {
        "capability": str(capability)[:100],
        "rating": rating,
        "note": str(note)[:500],
        "request_id": (request_id or "")[:64],
    }
    store.record_event("feedback", payload)
    return payload


def feedback_summary(
    store: FabricStore, limit: int = MAX_EVENTS, prior: float = PRIOR
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for event in store.list_events("feedback", limit):
        payload = event["payload"]
        name = str(payload.get("capability", ""))
        if not name:
            continue
        bucket = buckets.setdefault(
            name, {"capability": name, "count": 0, "positive": 0, "negative": 0, "neutral": 0}
        )
        rating = int(payload.get("rating", 0))
        bucket["count"] += 1
        if rating > 0:
            bucket["positive"] += 1
        elif rating < 0:
            bucket["negative"] += 1
        else:
            bucket["neutral"] += 1
    rows = []
    for bucket in buckets.values():
        rows.append(
            {
                **bucket,
                "score": round(
                    (bucket["positive"] - bucket["negative"])
                    / (bucket["count"] + max(1.0, float(prior))),
                    6,
                ),
            }
        )
    rows.sort(key=lambda row: (-row["score"], row["capability"]))
    return rows


def feedback_scores(
    store: FabricStore, limit: int = MAX_EVENTS, prior: float = PRIOR
) -> dict[str, float]:
    return {
        row["capability"]: row["score"]
        for row in feedback_summary(store, limit, prior)
    }
