"""Self-repair: quarantine capabilities whose entries cannot be imported.

Repair only touches built-ins whose entry is missing or not callable. It never
deletes history and never fabricates a replacement for an unknown capability;
a known native or extra name is re-admitted at the next version.
"""

from __future__ import annotations

import importlib
from typing import Any

from .capabilities import NATIVE_SPEC, CapabilityRegistry
from .diagnostics import diagnose
from .evolution import EvolutionEngine
from .extras import EXTRAS
from .models import Capability, Provenance


def _entry_ok(capability: Capability) -> bool:
    module_name, _, func_name = capability.entry.partition(":")
    try:
        module = importlib.import_module(module_name)
        return callable(getattr(module, func_name, None))
    except Exception:
        return False


def _restore(registry: CapabilityRegistry, name: str) -> bool:
    native = next((spec for spec in NATIVE_SPEC if spec[0] == name), None)
    if native is not None:
        _, func, description, inputs, outputs = native
        registry.register(
            Capability(
                name=name,
                description=description,
                inputs=inputs,
                outputs=outputs,
                kind="builtin",
                entry=f"sovereign.native:{func}",
                provenance=Provenance(
                    source="builtin", url="", license="internal", confidence=1.0
                ),
            )
        )
        return True
    extra = EXTRAS.get(name)
    if extra is not None:
        func, description, inputs, outputs = extra
        registry.register(
            Capability(
                name=name,
                description=description,
                inputs=inputs,
                outputs=outputs,
                kind="builtin",
                entry=f"{func.__module__}:{func.__name__}",
                provenance=Provenance(
                    source="builtin", url="", license="internal", confidence=1.0
                ),
            )
        )
        return True
    return False


def repair(engine: EvolutionEngine) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    quarantined: list[str] = []
    for capability in engine.registry.list_active():
        if capability.kind != "builtin" or _entry_ok(capability):
            continue
        if engine.registry.quarantine(capability.name, capability.version):
            quarantined.append(capability.name)
            actions.append(
                {
                    "action": "quarantined",
                    "capability": capability.name,
                    "version": capability.version,
                }
            )
    for name in quarantined:
        if _restore(engine.registry, name):
            active = engine.registry.active(name)
            actions.append(
                {
                    "action": "restored",
                    "capability": name,
                    "version": None if active is None else active.version,
                }
            )
    report = diagnose(engine, include_security=False)
    if actions:
        engine.store.record_event(
            "self_repair",
            {"actions": actions, "remaining_issues": report["issues"]},
        )
    return {
        "ok": report["ok"],
        "actions": actions,
        "remaining_issues": report["issues"],
        "capabilities": report["capabilities"],
    }
