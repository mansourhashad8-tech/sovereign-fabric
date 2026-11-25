"""Capability-demand ledger built from protocol escalations.

Every escalation is a measured gap, not a failure to hide. The ledger stores a
request hash and structured reasons, never the raw request. Repeated gaps become
visible demand that a later capability can be designed against.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from .store import FabricStore


def request_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def record_run(store: FabricStore, report: dict[str, Any]) -> None:
    final = report.get("final_validation") or {}
    best = report.get("best_attempt") or {}
    store.record_event(
        "protocol.run",
        {
            "status": report.get("status"),
            "verified": bool(report.get("verified")),
            "goal_type": report.get("goal_type"),
            "route": best.get("name"),
            "request_hash": report.get("request_hash"),
            "duration_s": report.get("duration_s"),
            "failures": list(final.get("failures") or []),
            "scores": dict(best.get("scores") or {}),
            "freshness_score": final.get("freshness_score"),
        },
    )
    if report.get("status") != "escalation_required":
        return
    store.record_event(
        "protocol.gap",
        {
            "goal_type": report.get("goal_type"),
            "route": best.get("name"),
            "request_hash": report.get("request_hash"),
            "failures": list(final.get("failures") or []),
            "scores": dict(best.get("scores") or {}),
            "next_actions": list(report.get("next_actions") or []),
            "freshness_score": final.get("freshness_score"),
        },
    )


_DEMANDS = {
    "guardianship": ("source_connector", "connect an external source or local corpus"),
    "comprehensiveness": ("multi_source_retrieval", "retrieve from at least two sources"),
    "recency": ("freshness_retrieval", "add a recent-source query path"),
    "speed": ("fast_path", "add a lower-latency execution path"),
    "constraint_transcendence": ("synthesis_spec", "add a synthesis or constraint adapter"),
    "determinism": ("deterministic_replay", "add a reproducible replay path"),
    "planning": ("capability_bridge", "add a bridge capability for the missing type"),
}


def _demands(failure_counts: Counter[str]) -> list[dict[str, Any]]:
    demands: list[dict[str, Any]] = []
    for reason, count in failure_counts.most_common():
        key = reason.split("=", 1)[0].split()[0].strip().lower()
        proposal, action = _DEMANDS.get(key, ("capability_for_" + key, "design a bounded capability"))
        demands.append(
            {
                "proposed_capability": proposal,
                "reason": reason,
                "count": count,
                "next_action": action,
                "status": "demand",
                "auto_created": False,
            }
        )
    return demands


def gap_summary(store: FabricStore, limit: int = 100) -> dict[str, Any]:
    limit = max(1, min(int(limit), 500))
    gaps = store.list_events("protocol.gap", limit=limit)
    runs = store.list_events("protocol.run", limit=limit)
    goal_counts: Counter[str] = Counter()
    failure_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    for event in gaps:
        payload = event["payload"]
        goal_counts[str(payload.get("goal_type") or "unknown")] += 1
        failure_counts.update(str(item) for item in payload.get("failures") or [])
        for key, value in (payload.get("scores") or {}).items():
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if numeric < 0.5:
                failure_counts[f"{key}={numeric:.2f} below 0.50"] += 1
        action_counts.update(str(item) for item in payload.get("next_actions") or [])
    return {
        "runs": len(runs),
        "verified": sum(1 for event in runs if event["payload"].get("verified")),
        "escalated": len(gaps),
        "goal_types": [
            {"goal_type": name, "count": count}
            for name, count in goal_counts.most_common()
        ],
        "failure_reasons": [
            {"reason": name, "count": count}
            for name, count in failure_counts.most_common()
        ],
        "next_actions": [
            {"action": name, "count": count}
            for name, count in action_counts.most_common()
        ],
        "proposed_capabilities": _demands(failure_counts),
        "recent": [
            {
                "ts": event["ts"],
                "goal_type": event["payload"].get("goal_type"),
                "route": event["payload"].get("route"),
                "request_hash": event["payload"].get("request_hash"),
                "failures": event["payload"].get("failures") or [],
                "next_actions": event["payload"].get("next_actions") or [],
            }
            for event in gaps[:20]
        ],
        "privacy": "request text is never stored; only a 16-hex-character hash",
        "automatic_capability_creation": False,
    }


def protocol_history(store: FabricStore, limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    return {
        "runs": store.list_events("protocol.run", limit=limit),
        "gaps": store.list_events("protocol.gap", limit=limit),
        "note": "append-only event history; not a reinforcement-learning trace",
    }
