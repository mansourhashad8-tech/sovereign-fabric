"""Append-only decision memory for protocol runs.

A decision record keeps the structured basis of a choice: route, scores,
alternatives, and next actions. It never keeps the raw request. The ledger is
for audit and exact-hash reuse checks; it does not automatically reuse or
rewrite a decision.
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from .store import FabricStore


def record_decision(store: FabricStore, report: dict[str, Any]) -> dict[str, Any]:
    best = report.get("best_attempt") or {}
    final = report.get("final_validation") or {}
    alternatives = []
    for attempt in report.get("alternatives") or []:
        alternatives.append(
            {
                "route": attempt.get("name"),
                "validator_passed": bool(attempt.get("validator_passed")),
                "execution_ok": bool(attempt.get("execution_ok")),
                "failures": list(attempt.get("failures") or []),
            }
        )
    payload = {
        "decision_id": uuid.uuid4().hex[:12],
        "request_hash": report.get("request_hash"),
        "reuse_key": report.get("request_hash"),
        "goal_type": report.get("goal_type"),
        "status": report.get("status"),
        "verified": bool(report.get("verified")),
        "route": best.get("name"),
        "scores": dict(best.get("scores") or {}),
        "alternatives": alternatives,
        "next_actions": list(report.get("next_actions") or []),
        "rationale": (
            "highest-ranked route that passed execution and the six-criterion validator"
            if report.get("verified")
            else "highest-ranked route after all bounded alternatives were tried"
        ),
        "automatic_reuse": False,
        "final_validator_passed": bool(final.get("validator_passed")),
    }
    store.record_event("decision.record", payload)
    return payload


def decision_summary(store: FabricStore, limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    events = store.list_events("decision.record", limit=limit)
    routes: Counter[str] = Counter()
    goals: Counter[str] = Counter()
    hashes: Counter[str] = Counter()
    for event in events:
        payload = event["payload"]
        routes[str(payload.get("route") or "unknown")] += 1
        goals[str(payload.get("goal_type") or "unknown")] += 1
        if payload.get("reuse_key"):
            hashes[str(payload["reuse_key"])] += 1
    return {
        "decisions": len(events),
        "verified": sum(1 for event in events if event["payload"].get("verified")),
        "escalated": sum(
            1 for event in events if event["payload"].get("status") == "escalation_required"
        ),
        "routes": [{"route": name, "count": count} for name, count in routes.most_common()],
        "goal_types": [{"goal_type": name, "count": count} for name, count in goals.most_common()],
        "reuse_candidates": [
            {"request_hash": key, "count": count}
            for key, count in hashes.most_common()
            if count > 1
        ],
        "recent": [
            {
                "ts": event["ts"],
                "decision_id": event["payload"].get("decision_id"),
                "request_hash": event["payload"].get("request_hash"),
                "goal_type": event["payload"].get("goal_type"),
                "status": event["payload"].get("status"),
                "route": event["payload"].get("route"),
                "verified": event["payload"].get("verified"),
            }
            for event in events[:20]
        ],
        "privacy": "no raw request is stored; reuse_key is a 16-hex request hash",
        "automatic_reuse": False,
    }


def lookup_decisions(
    store: FabricStore, request_hash: str, limit: int = 20
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 100))
    matches = [
        event
        for event in store.list_events("decision.record", limit=5000)
        if event["payload"].get("request_hash") == request_hash
    ][:limit]
    return {
        "request_hash": request_hash,
        "decisions": matches,
        "count": len(matches),
        "automatic_reuse": False,
    }
