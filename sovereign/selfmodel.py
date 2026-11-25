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

_GOALS = (
    "markdown",
    "summary",
    "tokens",
    "counts",
    "report",
    "keywords",
    "sentences",
    "text_stats",
    "redacted_text",
    "digest",
    "stems",
    "headings",
    "text_excerpt",
)


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
            "Embeddings are deterministic, Arabic-aware lexical hashes, not a semantic model.",
            "The planner is classical A*, not quantum and not parallel beyond its own search.",
            "Synthesis fits the examples it is given; it does not infer arbitrary intent.",
            "The continuous loop is a bounded scheduler with a stop button.",
            "No custody, no private keys, and no user gas are involved.",
            "No quantum hardware and no HPC endpoint are configured.",
            "The validator is auditable and tested, but it can still be wrong.",
            "The Arabic stemmer is a light prefix/suffix rule set, not morphology.",
            "Feedback is a smoothed vote that reorders search and weights planner costs; it does not train a model.",
            "Automatic outcome feedback rewards executed steps, so it can reinforce a route that runs but is not useful.",
            "Runtime settings are allowlisted and bounded; validation thresholds and security invariants are not settable.",
            "The context packet is a read-only join; its candidate links are not verified relationships.",
            "Selfhood is a functional model and a bounded initiative, not consciousness, life, or a sovereign will.",
            "The physical side of the reality bridge is absent; physical intents are refused, not executed.",
            "The cosmic module generates protocols and simulates scenarios; it does not see the future, reverse causality, or harvest cosmic energy.",
            "Self-repair restores known built-ins with broken import entries; it cannot invent missing code.",
            "External expert answers are unverified text and are never executed.",
            "Media capabilities read headers only; there is no OCR, vision, or audio transcription.",
            "The immune system is an online statistical detector, not deep learning; its state is in-process.",
            "Collective memory is a manual anonymized JSON exchange, not federated learning or a global brain.",
            "The autonomy gate checks operational evidence, not life or consciousness.",
            "The deterministic protocol tries bounded routes; escalation_required means no route passed all six criteria, not a verified result.",
            "Freshness is counted within a 180-day window; older knowledge is not scored as recent.",
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

    def calibration(self) -> dict[str, Any]:
        cycles = list(reversed(self.engine.store.list_events("cycle", 500)))
        history: dict[str, list[int]] = {}
        brier_terms: list[float] = []
        rows: list[dict[str, Any]] = []
        for event in cycles:
            payload = event.get("payload", {})
            goal = str(payload.get("goal_type", "unknown"))
            actual = 1 if payload.get("ok") else 0
            passed, total = history.get(goal, [0, 0])
            predicted = (passed + 1.0) / (total + 2.0)
            term = (predicted - actual) ** 2
            brier_terms.append(term)
            rows.append(
                {
                    "goal": goal,
                    "predicted": round(predicted, 6),
                    "actual": actual,
                    "brier": round(term, 6),
                }
            )
            history[goal] = [passed + actual, total + 1]
        brier = sum(brier_terms) / len(brier_terms) if brier_terms else 0.0
        baseline = 0.25 if brier_terms else 0.0
        by_goal = {
            goal: {
                "cycles": total,
                "passed": passed,
                "rate": round(passed / total, 6) if total else 0.0,
            }
            for goal, (passed, total) in sorted(history.items())
        }
        return {
            "cycles": len(rows),
            "brier": round(brier, 6),
            "baseline_brier": baseline,
            "skill": round(1.0 - brier / baseline, 6) if baseline else 0.0,
            "by_goal": by_goal,
            "rows": rows[-20:],
            "method": "prequential Laplace prediction; each cycle is scored before its outcome is added",
            "note": "small samples make this a diagnostic, not a guarantee",
        }

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
            "calibration": self.calibration(),
            "generated_at": utcnow(),
        }
