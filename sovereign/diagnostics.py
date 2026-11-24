"""Read-only self-diagnostics: database, registry, entries, planner, security."""

from __future__ import annotations

import importlib
from collections import Counter
from typing import Any

from .evolution import EvolutionEngine
from .pathfinder import operators_from
from .security import audit as security_audit


def diagnose(engine: EvolutionEngine, include_security: bool = True) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    issues: list[str] = []

    def check(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            issues.append(f"{name}: {detail}")

    try:
        units = engine.store.count_knowledge()
        check("database", True, {"knowledge_units": units})
    except Exception as exc:
        check("database", False, f"{type(exc).__name__}: {exc}")

    active = engine.registry.list_active()
    check("capabilities", bool(active), {"active": len(active)})

    names = Counter(cap.name for cap in active)
    duplicates = sorted(name for name, count in names.items() if count > 1)
    check("capability_names", not duplicates, {"duplicates": duplicates})

    missing: list[str] = []
    for cap in active:
        if cap.kind != "builtin":
            continue
        module_name, _, func_name = cap.entry.partition(":")
        try:
            module = importlib.import_module(module_name)
            if not callable(getattr(module, func_name, None)):
                missing.append(cap.name)
        except Exception:
            missing.append(cap.name)
    check("capability_entries", not missing, {"missing": missing})

    try:
        plan = engine.pathfinder.plan(
            ("text",), "markdown", operators_from(active)
        )
        check(
            "planner",
            plan.solved,
            {"goal": "markdown", "steps": [step.capability for step in plan.steps]},
        )
    except Exception as exc:
        check("planner", False, f"{type(exc).__name__}: {exc}")

    guardians = engine.guardians.names()
    check("guardians", bool(guardians), {"count": len(guardians)})

    security: dict[str, Any] | None = None
    if include_security:
        try:
            report = security_audit("sovereign", online=False)
            security = {
                "findings": report.get("finding_counts", {}),
                "openness_passed": report.get("openness_passed"),
                "source_files": len(report.get("source_files", [])),
            }
            counts = security["findings"] or {}
            check(
                "security_scan",
                not counts.get("critical") and not counts.get("high"),
                security,
            )
        except Exception as exc:
            check("security_scan", False, f"{type(exc).__name__}: {exc}")

    return {
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
        "issues": issues,
        "capabilities": len(active),
        "guardians": guardians,
        "security": security,
    }
