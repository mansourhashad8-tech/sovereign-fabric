"""Allowlisted runtime settings with hard bounds, audit, and rollback.

Only parameters that change search and scheduling behaviour are settable.
Validation thresholds, security invariants, and capability admission rules are
deliberately absent: a settings API must not be able to lower the system's own
standards. Every change is recorded with its old value, new value, and reason.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .models import utcnow
from .store import FabricStore


@dataclass(frozen=True)
class Spec:
    default: Any
    kind: str
    minimum: float | None
    maximum: float | None
    description: str


SPECS: dict[str, Spec] = {
    "planner.feedback_scale": Spec(
        0.25, "float", 0.0, 0.5,
        "how strongly feedback changes a capability's planning cost",
    ),
    "planner.cost_floor": Spec(
        0.5, "float", 0.25, 1.0,
        "minimum cost of one planning step",
    ),
    "planner.cost_ceiling": Spec(
        1.5, "float", 1.0, 2.0,
        "maximum cost of one planning step",
    ),
    "feedback.prior": Spec(
        5.0, "float", 1.0, 50.0,
        "Laplace-like prior that smooths a capability's feedback score",
    ),
    "auto_feedback.enabled": Spec(
        True, "bool", None, None,
        "record +1/-1 feedback from execution outcomes",
    ),
}


def _coerce(key: str, value: Any) -> Any:
    spec = SPECS.get(key)
    if spec is None:
        raise KeyError(f"unknown setting: {key}")
    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
        return value
    if isinstance(value, bool):
        raise ValueError(f"{key} must be numeric, not boolean")
    if spec.kind == "float":
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be a number") from exc
        if not math.isfinite(number):
            raise ValueError(f"{key} must be finite")
    elif spec.kind == "int":
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer") from exc
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"{key} must be an integer")
    else:
        raise ValueError(f"{key} has an unknown kind")
    if spec.minimum is not None and number < spec.minimum:
        raise ValueError(f"{key} must be at least {spec.minimum}")
    if spec.maximum is not None and number > spec.maximum:
        raise ValueError(f"{key} must be at most {spec.maximum}")
    return number


class Settings:
    def __init__(self, store: FabricStore) -> None:
        self.store = store

    def get(self, key: str) -> Any:
        spec = SPECS.get(key)
        if spec is None:
            raise KeyError(f"unknown setting: {key}")
        raw = self.store.get_setting(key)
        return spec.default if raw is None else _coerce(key, raw)

    def snapshot(self) -> dict[str, Any]:
        stored = self.store.all_settings()
        values = {}
        for key, spec in SPECS.items():
            values[key] = {
                "value": _coerce(key, stored[key]) if key in stored else spec.default,
                "default": spec.default,
                "kind": spec.kind,
                "minimum": spec.minimum,
                "maximum": spec.maximum,
                "description": spec.description,
                "modified": key in stored,
            }
        return {
            "settings": values,
            "revision": len(self.store.list_events("settings.changed", 1000)),
            "note": "only allowlisted search and scheduling parameters are settable; validation and security rules are not",
        }

    def set(self, key: str, value: Any, reason: str = "") -> dict[str, Any]:
        if key not in SPECS:
            raise KeyError(f"unknown setting: {key}")
        old = self.get(key)
        new = _coerce(key, value)
        self.store.set_setting(key, new, utcnow())
        self.store.record_event(
            "settings.changed",
            {
                "key": key,
                "old": old,
                "new": new,
                "reason": str(reason)[:300],
            },
        )
        return {"key": key, "old": old, "new": new, "reason": str(reason)[:300]}

    def reset(self, key: str | None = None, reason: str = "") -> dict[str, Any]:
        keys = [key] if key is not None else list(SPECS)
        changed = []
        for item in keys:
            if item not in SPECS:
                raise KeyError(f"unknown setting: {item}")
            old = self.get(item)
            self.store.delete_setting(item)
            new = SPECS[item].default
            if old != new:
                changed.append({"key": item, "old": old, "new": new})
            self.store.record_event(
                "settings.changed",
                {
                    "key": item,
                    "old": old,
                    "new": new,
                    "reason": str(reason or "reset")[:300],
                },
            )
        return {"reset": keys, "changed": changed}

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.store.list_events("settings.changed", max(1, min(int(limit), 500)))

    def tune(self) -> dict[str, Any]:
        cycles = list(reversed(self.store.list_events("cycle", 200)))
        if len(cycles) < 20:
            return {
                "changed": False,
                "reason": "need at least 20 cycles before tuning",
                "cycles": len(cycles),
            }
        passed = total = 0
        terms = []
        for event in cycles:
            payload = event.get("payload", {})
            actual = 1 if payload.get("ok") else 0
            predicted = (passed + 1.0) / (total + 2.0)
            terms.append((predicted - actual) ** 2)
            passed += actual
            total += 1
        brier = sum(terms) / len(terms)
        skill = 1.0 - brier / 0.25
        current = self.get("planner.feedback_scale")
        if skill < 0.0:
            target = max(0.0, current - 0.05)
        elif skill > 0.1:
            target = min(0.5, current + 0.05)
        else:
            target = current
        if target == current:
            return {
                "changed": False,
                "cycles": len(cycles),
                "brier": round(brier, 6),
                "skill": round(skill, 6),
                "value": current,
                "reason": "skill is inside the no-change band",
            }
        self.set(
            "planner.feedback_scale",
            target,
            reason=f"bounded tune from prequential skill {skill:.3f}",
        )
        return {
            "changed": True,
            "cycles": len(cycles),
            "brier": round(brier, 6),
            "skill": round(skill, 6),
            "old": current,
            "new": target,
            "reason": "bounded heuristic: lower the feedback scale when self-prediction is worse than 0.25, raise it when clearly better",
        }
