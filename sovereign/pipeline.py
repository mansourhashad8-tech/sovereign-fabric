"""Compose capabilities into a bounded pipeline.

Each step receives the previous step's ``value`` under ``value`` and may add
its own parameters. A failing step stops the pipeline and returns the partial
trace; it never raises past the caller's boundary.
"""

from __future__ import annotations

from typing import Any

from .capabilities import CapabilityRegistry

MAX_STEPS = 20


def run_pipeline(
    registry: CapabilityRegistry, steps: list[dict[str, Any]]
) -> dict[str, Any]:
    if not steps:
        raise ValueError("pipeline needs at least one step")
    if len(steps) > MAX_STEPS:
        raise ValueError(f"pipeline is limited to {MAX_STEPS} steps")

    trace: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for index, step in enumerate(steps):
        name = str(step.get("capability", "")).strip()
        if not name:
            return {
                "ok": False,
                "failed_at": index,
                "error": "step has no capability",
                "steps": trace,
            }
        payload = dict(step.get("payload") or {})
        if index and "value" not in payload and previous is not None:
            payload["value"] = previous.get("value")
        try:
            result = registry.invoke(name, payload)
        except Exception as exc:
            return {
                "ok": False,
                "failed_at": index,
                "error": f"{type(exc).__name__}: {exc}",
                "steps": trace,
            }
        if not isinstance(result, dict):
            result = {"value": result}
        trace.append({"capability": name, "result": result})
        previous = result
    return {
        "ok": True,
        "value": previous.get("value") if previous is not None else None,
        "steps": trace,
    }
