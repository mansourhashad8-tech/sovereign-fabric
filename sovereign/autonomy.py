"""Autonomy and continuous-evolution gate.

The gate does not prove life or consciousness. It checks four operational
conditions: local capability autonomy, loop continuity, safety evidence, and at
least one anonymized collective lesson. A failed condition is reported, never
rounded up.
"""

from __future__ import annotations

from typing import Any

from .security import audit as security_audit
from .store import FabricStore


def reward_ledger(store: FabricStore, limit: int = 2_000) -> dict[str, Any]:
    """A transparent heuristic ledger, not reinforcement learning."""
    components = {
        "evolution_passed": 0,
        "evolution_failed": 0,
        "optimizations": 0,
        "repairs": 0,
        "immune_incidents": 0,
        "feedback_positive": 0,
        "feedback_negative": 0,
    }
    score = 0.0
    for event in store.list_events(None, limit):
        kind = event.get("kind")
        payload = event.get("payload") or {}
        if kind == "evolution":
            if payload.get("ok"):
                components["evolution_passed"] += 1
                score += 2.0
            else:
                components["evolution_failed"] += 1
                score -= 1.0
        elif kind == "capability.optimized":
            components["optimizations"] += 1
            score += 1.0
        elif kind == "self_repair":
            actions = len(payload.get("actions") or [])
            components["repairs"] += actions
            score += actions
        elif kind == "immune.incident":
            components["immune_incidents"] += 1
            score -= 2.0
        elif kind == "feedback":
            rating = int(payload.get("rating", 0) or 0)
            if rating > 0:
                components["feedback_positive"] += 1
                score += 1.0
            elif rating < 0:
                components["feedback_negative"] += 1
                score -= 1.0
    return {
        "score": round(score, 3),
        "components": components,
        "mode": "transparent event ledger, not reinforcement learning",
    }


def assess(
    engine,
    *,
    loop_status: dict[str, Any] | None = None,
    immune_status: dict[str, Any] | None = None,
    collective: dict[str, Any] | None = None,
    include_security: bool = True,
    security_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active = engine.registry.list_active()
    local_kinds = {cap.kind for cap in active}
    autonomy_ok = bool(active) and local_kinds <= {"builtin", "synthesized"}
    continuity_ok = bool(
        loop_status
        and (loop_status.get("running") or int(loop_status.get("generation", 0)) > 0)
    )

    findings: dict[str, int] = {}
    if security_report is None and include_security:
        try:
            security_report = security_audit("sovereign", online=False)
        except Exception as exc:
            security_report = {"error": f"{type(exc).__name__}: {exc}"}
    security_error = bool(security_report and security_report.get("error"))
    if security_report and "finding_counts" in security_report:
        findings = security_report.get("finding_counts") or {}
    security_ok = (
        not security_error
        and not findings.get("critical")
        and not findings.get("high")
    )
    safety_ok = security_ok and immune_status is not None

    lessons = int((collective or {}).get("lessons", 0) or 0)
    collective_ok = lessons > 0

    checks = {
        "autonomy": {
            "passed": autonomy_ok,
            "detail": {
                "active_capabilities": len(active),
                "kinds": sorted(local_kinds),
                "external_experts_required": False,
            },
        },
        "continuity": {
            "passed": continuity_ok,
            "detail": {
                "running": bool(loop_status and loop_status.get("running")),
                "generation": int((loop_status or {}).get("generation", 0) or 0),
            },
        },
        "safety": {
            "passed": safety_ok,
            "detail": {
                "security_findings": findings,
                "security_scan_skipped": not include_security,
                "immune_mode": (immune_status or {}).get("mode"),
                "quarantined": (immune_status or {}).get("quarantined"),
            },
        },
        "collective": {
            "passed": collective_ok,
            "detail": {
                "lessons": lessons,
                "exchange_mode": (collective or {}).get("exchange_mode"),
            },
        },
    }
    failed = [name for name, check in checks.items() if not check["passed"]]
    return {
        "passed": not failed,
        "checks": checks,
        "failed": failed,
        "reward": reward_ledger(engine.store),
        "note": (
            "operational gate only; this is not proof of life, consciousness, "
            "or exponential growth"
        ),
    }
