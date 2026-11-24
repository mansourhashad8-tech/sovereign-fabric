"""A self-model derived from evidence, not from a story.

The model reads the registry, the event log, the knowledge count, the guardian
list, and the planner. It can answer "can I reach this goal?" by actually
planning, and it states its limits in the same breath as its strengths.
"""

from __future__ import annotations

from statistics import median
from typing import Any

from .models import utcnow
from .pathfinder import operators_from
from .properties import check_capabilities

_GOALS = ("markdown", "summary", "tokens", "counts", "report")


class SelfModel:
    def __init__(self, engine) -> None:
        self.engine = engine

    def can(self, goal: str) -> dict[str, Any]:
        operators = operators_from(self.engine.registry.list_active())
        plan = self.engine.pathfinder.plan(("text",), goal, operators)
        return {
            "goal": goal,
            "possible": bool(plan.solved),
            "plan": [step.capability for step in plan.steps],
            "reason": plan.reason,
        }

    def profile(self) -> dict[str, Any]:
        store = self.engine.store
        cycles = [event["payload"] for event in store.list_events("cycle", 500)]
        capabilities = self.engine.registry.list_active()
        optimizations = [event["payload"] for event in store.list_events("capability.optimized", 100)]
        ticks = [event["payload"] for event in store.list_events("loop.tick", 1)]
        durations = [
            float(cycle["duration_s"])
            for cycle in cycles
            if isinstance(cycle.get("duration_s"), (int, float))
        ]
        by_goal: dict[str, dict[str, int]] = {}
        for cycle in cycles:
            goal = str(cycle.get("goal_type", "unknown"))
            bucket = by_goal.setdefault(goal, {"cycles": 0, "passed": 0})
            bucket["cycles"] += 1
            bucket["passed"] += int(bool(cycle.get("ok")))
        return {
            "capabilities": {
                "total": len(capabilities),
                "builtin": sum(1 for cap in capabilities if cap.kind == "builtin"),
                "synthesized": sum(1 for cap in capabilities if cap.kind == "synthesized"),
                "names": [cap.name for cap in capabilities],
            },
            "knowledge_units": store.count_knowledge(),
            "sources": self.engine.guardians.names(),
            "cycles": {
                "total": len(cycles),
                "passed": sum(1 for cycle in cycles if cycle.get("ok")),
                "median_duration_s": round(median(durations), 4) if durations else 0.0,
                "by_goal": by_goal,
            },
            "optimizations": {
                "count": len(optimizations),
                "last": optimizations[0] if optimizations else None,
            },
            "loop": {
                "generation": ticks[0].get("generation", 0) if ticks else 0,
                "last": ticks[0] if ticks else None,
            },
        }

    def _limits(self, profile: dict[str, Any]) -> list[str]:
        limits = [
            "Embeddings are deterministic lexical hashes, not a semantic model.",
            "The planner is classical A*, not quantum and not parallel beyond its own search.",
            "Synthesis fits the examples it is given; it does not infer arbitrary intent.",
            "The continuous loop is a bounded scheduler with a stop button.",
            "No custody, no private keys, and no user gas are involved.",
            "No quantum hardware and no HPC endpoint are configured.",
            "The validator is auditable and tested, but it can still be wrong.",
        ]
        if not self.engine.experts:
            limits.insert(
                0,
                "No external model expert is configured; acquisition is local-only.",
            )
        synthesized = profile["capabilities"]["synthesized"]
        if synthesized:
            limits.insert(
                0,
                f"{synthesized} synthesized capabilities are verified in a subprocess on every call.",
            )
        return limits

    def _verdict(
        self,
        profile: dict[str, Any],
        can: dict[str, Any],
        limits: list[str],
        properties: dict[str, Any],
    ) -> str:
        caps = profile["capabilities"]
        cycles = profile["cycles"]
        reachable = [goal for goal, result in can.items() if result["possible"]]
        unreachable = [goal for goal, result in can.items() if not result["possible"]]
        if cycles["total"]:
            rate = round(100.0 * cycles["passed"] / cycles["total"], 1)
            cycle_text = (
                f"{cycles['passed']} of {cycles['total']} recorded cycles passed every "
                f"criterion ({rate}%), with a median cycle of {cycles['median_duration_s']}s"
            )
        else:
            cycle_text = "No cycles have been recorded yet"
        return (
            f"Precise self-assessment: {caps['total']} active capabilities "
            f"({caps['builtin']} builtin, {caps['synthesized']} synthesized), "
            f"{profile['knowledge_units']} absorbed knowledge units, and "
            f"{len(profile['sources'])} external sources. {cycle_text}. "
            f"{profile['optimizations']['count']} measured optimizations are on record. "
            f"Reachable goals: {', '.join(reachable) or 'none'}. "
            f"Unreachable goals: {', '.join(unreachable) or 'none'}. "
            f"Property checks: {sum(item['passed'] for item in properties['capabilities'])}"
            f"/{sum(item['checks'] for item in properties['capabilities'])} passed. "
            f"{len(limits)} limits are declared. "
            "I am not conscious, not quantum, and not a million-fold accelerator."
        )

    def assess(self) -> dict[str, Any]:
        profile = self.profile()
        can = {goal: self.can(goal) for goal in _GOALS}
        limits = self._limits(profile)
        properties = check_capabilities(self.engine.registry, cases=8)
        verdict = self._verdict(profile, can, limits, properties)
        return {
            "verdict": verdict,
            "profile": profile,
            "can": can,
            "limits": limits,
            "properties": {
                "passed": properties["passed"],
                "checks": sum(item["checks"] for item in properties["capabilities"]),
                "failed": sum(item["failed"] for item in properties["capabilities"]),
            },
            "overclaims": self.engine.validator.detect_overclaims(verdict),
            "generated_at": utcnow(),
        }
