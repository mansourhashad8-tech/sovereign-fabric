"""A self-directed practice loop that chooses what to improve next.

The choice is a transparent heuristic: weak pass rate, high predictive
uncertainty, and a small exploration bonus. Practice runs one measured cycle
and records the before/after result. It does not promise improvement.
"""

from __future__ import annotations

from typing import Any

from .cosmic import CosmicProtocol
from .mastery import Mastery
from .models import utcnow

GOALS = (
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


class MetaCurriculum:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.store = engine.store
        self.cosmic = CosmicProtocol(engine)

    def table(self, scenarios: int = 200) -> list[dict[str, Any]]:
        mastery = Mastery(self.engine).table()
        rows = []
        for goal in GOALS:
            stats = mastery.get(goal, {"attempts": 0, "passed": 0, "rate": 0.0})
            predicted = self.cosmic.predict(goal, scenarios=scenarios, seed=0)
            probability = float(predicted.get("probability", 0.0))
            uncertainty = 4.0 * probability * (1.0 - probability)
            exploration = 0.2 if stats["attempts"] == 0 else 0.0
            stagnation = 0.1 * stats["attempts"] if stats["rate"] == 0.0 else 0.0
            priority = (1.0 - float(stats["rate"])) + uncertainty + exploration + stagnation
            rows.append(
                {
                    "goal": goal,
                    "attempts": stats["attempts"],
                    "passed": stats["passed"],
                    "rate": stats["rate"],
                    "possible": bool(predicted.get("possible")),
                    "predicted_success": round(probability, 6),
                    "uncertainty": round(uncertainty, 6),
                    "stagnation": round(stagnation, 6),
                    "priority": round(priority, 6),
                    "reason": "weak rate, predictive uncertainty, and stagnation",
                }
            )
        rows.sort(key=lambda row: (-row["priority"], row["goal"]))
        return rows

    def run(
        self,
        iterations: int = 1,
        budget_s: float = 8.0,
        scenarios: int = 200,
    ) -> dict[str, Any]:
        iterations = max(1, min(int(iterations), 5))
        budget_s = max(1.0, min(float(budget_s), 30.0))
        before = self.table(scenarios)
        runs = []
        for _ in range(iterations):
            choice = self.table(scenarios)[0]
            cycle = self.engine.evolve(
                f"meta practice {choice['goal']}",
                goal_type=choice["goal"],
                initial=("text",),
                text="alpha beta gamma",
                budget_s=budget_s,
                auto_extend=True,
                max_attempts=2,
                local_transform=True,
            )
            run = {
                "goal": choice["goal"],
                "predicted_success": choice["predicted_success"],
                "before_rate": choice["rate"],
                "ok": cycle.ok,
                "execution_ok": bool(cycle.execution.get("ok")),
                "passed": cycle.validation.passed,
                "plan": [step.capability for step in cycle.plan.steps],
                "duration_s": cycle.duration_s,
            }
            runs.append(run)
            self.store.record_event(
                "meta.practice",
                {
                    **run,
                    "at": utcnow(),
                    "note": "one bounded practice cycle; improvement is not guaranteed",
                },
            )
        after = self.table(scenarios)
        return {
            "before": before,
            "after": after,
            "runs": runs,
            "note": "self-directed practice, measured before and after; not a promise of improvement",
            "generated_at": utcnow(),
        }
