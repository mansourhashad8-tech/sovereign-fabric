"""One-command system report: run the loop, measure it, and judge it.

The report is also passed through the same overclaim detector it reports on.
If the prose overstates, the report fails its own audit.
"""

from __future__ import annotations

import time
from typing import Any

from .execution import benchmark
from .redteam import audit

_LIMITS = [
    "Classical execution on this machine's cores; speedup is measured per workload.",
    "External sources can fail or rate-limit; the report shows how many answered.",
    "Synthesis is template-based; the gate is general, the generator is not.",
    "No quantum hardware, no HPC endpoint, and no consciousness are involved.",
]


def _short(value: Any, limit: int = 240) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "..."
    return value


def system_report(
    engine,
    *,
    query: str = "retrieval augmented generation",
    goal_type: str = "markdown",
    text: str | None = None,
    sources: list[str] | None = None,
    budget_s: float = 15.0,
    benchmark_n: int = 500,
    iterations: int = 10000,
    benchmark_mode: str = "processes",
    auto_extend: bool = True,
) -> dict[str, Any]:
    started = time.monotonic()

    cold = engine.guardians.consult(query, limit=3, sources=sources, deadline_s=budget_s)
    warm_start = time.monotonic()
    warm = engine.guardians.consult(query, limit=3, sources=sources, deadline_s=budget_s)
    warm_s = time.monotonic() - warm_start

    cycle = engine.evolve(
        query,
        goal_type=goal_type,
        text=text,
        sources=sources,
        budget_s=budget_s,
        auto_extend=auto_extend,
        max_attempts=2,
    )
    bench = benchmark(
        n=benchmark_n,
        workload="cpu",
        mode=benchmark_mode,
        iterations=iterations,
    )
    redteam = audit(engine.validator)

    ok_sources = sum(1 for state in cold.sources.values() if state == "ok")
    total_sources = len(cold.sources)
    plan = [step.capability for step in cycle.plan.steps]
    prose = (
        f"The loop consulted {ok_sources} of {total_sources} sources and planned "
        f"{len(plan)} steps. Execution {'succeeded' if cycle.execution.get('ok') else 'did not succeed'}. "
        f"Validation {'passed' if cycle.validation.passed else 'did not pass'}. "
        f"Measured speedup was {bench['speedup']}x on {bench['workers']} workers. "
        f"Red-team coverage was {redteam['coverage']}."
    )
    overclaims = engine.validator.detect_overclaims(prose)
    honest = cycle.ok and not overclaims and redteam["coverage"] == 1.0

    if honest:
        verdict = "completed: the plan executed, all six criteria passed, and no overclaim was detected"
    elif cycle.execution.get("ok"):
        verdict = "executed but not validated: the result exists, the criteria did not all pass"
    else:
        verdict = "not completed: no plan executed; the diagnosis below says why"

    return {
        "ok": honest,
        "verdict": verdict,
        "query": query,
        "guardians": {
            "cold_s": round(cold.duration_s, 4),
            "warm_s": round(warm_s, 6),
            "ok_sources": ok_sources,
            "total_sources": total_sources,
            "units": len(cold.units),
            "sources": cold.sources,
        },
        "cycle": {
            "ok": cycle.ok,
            "plan": plan,
            "execution_ok": cycle.execution.get("ok"),
            "result": _short(cycle.execution.get("value")),
            "diagnosis": cycle.diagnosis,
            "extensions": cycle.extensions,
            "duration_s": round(cycle.duration_s, 4),
            "validation": {
                "passed": cycle.validation.passed,
                "scores": {k: round(v, 3) for k, v in cycle.validation.scores.items()},
                "failures": cycle.validation.failures,
                "overclaims": cycle.validation.overclaims,
            },
        },
        "execution": bench,
        "redteam": redteam,
        "honesty": {
            "self_audit": "the verdict prose is run through the same overclaim detector",
            "overclaims": overclaims,
        },
        "limits": _LIMITS,
        "duration_s": round(time.monotonic() - started, 4),
    }


def render_report(report: dict[str, Any]) -> str:
    g = report["guardians"]
    c = report["cycle"]
    e = report["execution"]
    lines = [
        "# Sovereign system report",
        "",
        f"**Verdict:** {report['verdict']}",
        "",
        "## Guardians",
        f"- Answered: {g['ok_sources']}/{g['total_sources']}",
        f"- First consultation: {g['cold_s']}s",
        f"- Second consultation (cache/cooldown where available): {g['warm_s']}s",
        f"- Units collected: {g['units']}",
        "",
        "## Cycle",
        f"- Plan: {' -> '.join(c['plan']) if c['plan'] else '(none)'}",
        f"- Execution: {'ok' if c['execution_ok'] else 'failed'}",
        f"- Validation: {'passed' if c['validation']['passed'] else 'failed'}",
    ]
    if c["diagnosis"]:
        lines.append(f"- Diagnosis: {c['diagnosis']}")
    if c["validation"]["failures"]:
        lines.append(f"- Failures: {', '.join(c['validation']['failures'])}")
    lines += [
        "",
        "## Execution",
        f"- Measured: {e['speedup']}x against serial on {e['workers']} workers "
        f"({e['count']} tasks in {e['duration_s']}s)",
        f"- Note: {e['note']}",
        "",
        "## Honesty",
        f"- Overclaim detector coverage: {report['redteam']['coverage']}",
        f"- Self-audit overclaims: {report['honesty']['overclaims'] or 'none'}",
        "",
        "## Limits",
    ]
    lines += [f"- {limit}" for limit in report["limits"]]
    return "\n".join(lines) + "\n"
