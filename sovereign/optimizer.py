"""Measured self-optimization: benchmark equivalent implementations, keep the faster.

A candidate is considered only if it produces byte-identical output to the
current implementation on a corpus of payloads. Timing is the second gate. If
no candidate beats the current implementation by a margin, nothing changes —
"no gain" is a valid result.
"""

from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from typing import Any, Callable

from .capabilities import CapabilityRegistry
from .models import Capability, Provenance


@dataclass(frozen=True)
class Variant:
    name: str
    entry: str


VARIANTS: dict[str, list[Variant]] = {
    "text.tokenize": [
        Variant("split", "sovereign.native:tokenize"),
        Variant("regex", "sovereign.native:tokenize_regex"),
    ],
    "tokens.count": [
        Variant("dict-loop", "sovereign.native:count_tokens"),
        Variant("counter", "sovereign.native:count_tokens_counter"),
    ],
    "counts.summarize": [
        Variant("sorted", "sovereign.native:summarize_counts"),
        Variant("heap", "sovereign.native:summarize_counts_heap"),
    ],
    "report.format": [
        Variant("join", "sovereign.native:format_report"),
        Variant("generator", "sovereign.native:format_report_generator"),
    ],
    "text.summarize": [
        Variant("split", "sovereign.native:extractive_summary"),
        Variant("regex", "sovereign.native:extractive_summary_regex"),
    ],
}

_WORDS = [
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    "iota", "kappa", "lambda", "mu", "nu", "xi", "omicron", "pi",
]


def _resolve(entry: str) -> Callable[[dict[str, Any]], Any]:
    module_name, _, func_name = entry.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, func_name)


def _corpus(name: str) -> list[dict[str, Any]]:
    if name == "text.tokenize":
        return [
            {"value": " ".join(_WORDS[i % len(_WORDS)] for i in range(n))}
            for n in (200, 2000, 10000)
        ]
    if name == "tokens.count":
        return [
            {"value": [_WORDS[i % len(_WORDS)] for i in range(n)]}
            for n in (2000, 10000, 50000)
        ]
    if name == "counts.summarize":
        return [
            {"value": {f"w{i}": (i * 7) % 50 for i in range(n)}}
            for n in (1000, 5000, 20000)
        ]
    if name == "report.format":
        return [
            {"value": {"top": [[f"w{i}", i] for i in range(n)], "distinct": n}}
            for n in (5, 50, 500)
        ]
    if name == "text.summarize":
        sentence = "This is a sentence about retrieval and planning. "
        return [{"value": sentence * n + "Final question?"} for n in (5, 50, 500)]
    return []


def _time(func: Callable[[dict[str, Any]], Any], payloads: list[dict[str, Any]], repeats: int) -> float:
    started = time.perf_counter()
    for _ in range(repeats):
        for payload in payloads:
            func(payload)
    elapsed = time.perf_counter() - started
    return elapsed / max(1, repeats * len(payloads))


class Optimizer:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def optimize(self, name: str, repeats: int = 10, margin: float = 0.95) -> dict[str, Any]:
        current = self.registry.active(name)
        if current is None:
            return {"name": name, "chosen": None, "reason": "no active capability"}
        payloads = _corpus(name)
        if not payloads:
            return {"name": name, "chosen": None, "reason": "no corpus for this capability"}

        try:
            current_func = _resolve(current.entry)
            expected = [current_func(payload) for payload in payloads]
            baseline = _time(current_func, payloads, repeats)
        except Exception as exc:
            return {"name": name, "chosen": None, "reason": f"current implementation failed: {exc}"}

        measured: list[dict[str, Any]] = []
        for variant in VARIANTS.get(name, []):
            if variant.entry == current.entry:
                continue
            try:
                func = _resolve(variant.entry)
                same = all(func(payload) == want for payload, want in zip(payloads, expected))
            except Exception as exc:
                measured.append(
                    {"name": variant.name, "entry": variant.entry, "verified": False,
                     "reason": f"{type(exc).__name__}: {exc}"}
                )
                continue
            if not same:
                measured.append(
                    {"name": variant.name, "entry": variant.entry, "verified": False,
                     "reason": "different output on the corpus"}
                )
                continue
            elapsed = _time(func, payloads, repeats)
            measured.append(
                {
                    "name": variant.name,
                    "entry": variant.entry,
                    "verified": True,
                    "duration_s": round(elapsed, 9),
                    "speedup": round(baseline / elapsed, 3) if elapsed else 0.0,
                }
            )

        faster = [item for item in measured if item.get("verified") and item["duration_s"] < baseline * margin]
        best = min(faster, key=lambda item: item["duration_s"]) if faster else None
        result: dict[str, Any] = {
            "name": name,
            "current": {
                "entry": current.entry,
                "version": current.version,
                "duration_s": round(baseline, 9),
            },
            "chosen": None,
            "speedup": 1.0,
            "variants": measured,
        }
        if best is None:
            result["reason"] = "no verified variant beat the current implementation by 5%"
            return result

        capability = Capability(
            name=name,
            description=current.description,
            inputs=current.inputs,
            outputs=current.outputs,
            kind="builtin",
            entry=best["entry"],
            provenance=Provenance(
                source="optimizer", url="", license="internal", confidence=1.0
            ),
            spec={"optimized_from": current.entry},
        )
        registered = self.registry.register(capability, activate=True)
        speedup = round(baseline / best["duration_s"], 3)
        result.update(
            {
                "chosen": best["name"],
                "entry": best["entry"],
                "speedup": speedup,
                "version": registered.version,
                "reason": f"verified identical output; {speedup}x faster",
            }
        )
        self.registry.store.record_event(
            "capability.optimized",
            {
                "name": name,
                "from": current.entry,
                "to": best["entry"],
                "version": registered.version,
                "speedup": result["speedup"],
            },
        )
        return result

    def optimize_all(self, repeats: int = 10) -> list[dict[str, Any]]:
        return [self.optimize(name, repeats=repeats) for name in VARIANTS]
