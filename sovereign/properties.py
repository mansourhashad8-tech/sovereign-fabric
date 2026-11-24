"""Property checks over the native capability chain.

These are invariants, not proofs. They generate random payloads and assert
things that must hold for any correct implementation, so an optimized variant
cannot quietly change the contract.
"""

from __future__ import annotations

import random
import time
from typing import Any

_WORDS = [
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    "iota", "kappa", "lambda", "mu", "nu", "xi", "omicron", "pi", "rho",
    "sigma", "tau", "upsilon", "phi", "chi", "psi", "omega", "data", "model",
]


def _failures(registry, cases: int, seed: int) -> dict[str, dict[str, Any]]:
    rng = random.Random(seed)
    results: dict[str, dict[str, Any]] = {}

    def bucket(name: str) -> dict[str, Any]:
        return results.setdefault(name, {"checks": 0, "passed": 0, "failures": []})

    def record(name: str, ok: bool, detail: str = "") -> None:
        entry = bucket(name)
        entry["checks"] += 1
        if ok:
            entry["passed"] += 1
        elif len(entry["failures"]) < 3:
            entry["failures"].append(detail)

    def invoke(name: str, payload: dict[str, Any]) -> Any | None:
        try:
            return registry.invoke(name, payload)
        except Exception as exc:
            record(name, False, f"invoke failed: {type(exc).__name__}: {exc}")
            return None

    for _ in range(cases):
        text = " ".join(rng.choice(_WORDS) for _ in range(rng.randint(0, 15)))
        result = invoke("text.tokenize", {"value": text})
        if result is None:
            continue
        got = result["value"]
        record("text.tokenize", got == text.split(), f"{got!r} != {text.split()!r}")

    for _ in range(cases):
        tokens = [rng.choice(_WORDS) for _ in range(rng.randint(0, 50))]
        result = invoke("tokens.count", {"value": tokens})
        if result is None:
            continue
        counts = result["value"]
        ok = (
            sum(counts.values()) == len(tokens)
            and set(counts) == set(tokens)
            and all(value > 0 for value in counts.values())
        )
        record("tokens.count", ok, f"counts={counts!r} tokens={tokens!r}")

    for _ in range(cases):
        chosen = rng.sample(_WORDS, rng.randint(0, 10))
        counts = {word: rng.randint(1, 20) for word in chosen}
        result = invoke("counts.summarize", {"value": counts})
        if result is None:
            continue
        out = result["value"]
        expected = [list(pair) for pair in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]
        record(
            "counts.summarize",
            out.get("distinct") == len(counts) and out.get("top") == expected,
            f"{out!r} != distinct={len(counts)} top={expected!r}",
        )

    for _ in range(cases):
        top = [[f"w{i}", rng.randint(0, 9)] for i in range(rng.randint(0, 8))]
        result = invoke("report.format", {"value": {"top": top, "distinct": len(top)}})
        if result is None:
            continue
        out = result["value"]
        expected = "\n".join(f"- {key}: {value}" for key, value in top) if top else "(empty)"
        record("report.format", out == expected, f"{out!r} != {expected!r}")

    for _ in range(cases):
        sentence = " ".join(rng.choice(_WORDS) for _ in range(rng.randint(1, 10)))
        text = f"{sentence}. Second sentence! Third?"
        result = invoke("text.summarize", {"value": text})
        if result is None:
            continue
        out = result["value"]
        record("text.summarize", bool(out) and out in text, f"{out!r} not in {text!r}")

    return results


def check_capabilities(registry, cases: int = 30, seed: int = 0) -> dict[str, Any]:
    started = time.perf_counter()
    results = _failures(registry, max(1, cases), seed)
    capabilities = [
        {
            "name": name,
            "checks": entry["checks"],
            "passed": entry["passed"],
            "failed": entry["checks"] - entry["passed"],
            "failures": entry["failures"],
        }
        for name, entry in sorted(results.items())
    ]
    return {
        "cases": cases,
        "passed": all(item["failed"] == 0 for item in capabilities),
        "capabilities": capabilities,
        "duration_s": round(time.perf_counter() - started, 4),
    }
