"""Mastery tracking: find the weakest goal and practise it.

The table is derived from recorded cycles. Practice is a real cycle with
auto-extension enabled, so an unreachable goal can be acquired if a verified
blueprint exists. Improvement is not guaranteed, and the before/after tables
show that honestly.
"""

from __future__ import annotations

from typing import Any


class Mastery:
    def __init__(self, engine) -> None:
        self.engine = engine

    def table(self) -> dict[str, dict[str, Any]]:
        cycles = [event["payload"] for event in self.engine.store.list_events("cycle", 500)]
        table: dict[str, dict[str, Any]] = {}
        for cycle in cycles:
            goal = str(cycle.get("goal_type", "unknown"))
            row = table.setdefault(
                goal, {"attempts": 0, "passed": 0, "rate": 0.0, "last_request": None}
            )
            row["attempts"] += 1
            row["passed"] += int(bool(cycle.get("ok")))
            row["last_request"] = cycle.get("request")
        for row in table.values():
            row["rate"] = round(row["passed"] / row["attempts"], 3) if row["attempts"] else 0.0
        return table

    def weakest(self) -> str:
        table = self.table()
        if not table:
            return "markdown"
        return min(table, key=lambda goal: (table[goal]["rate"], -table[goal]["attempts"], goal))

    def practice(
        self,
        iterations: int = 1,
        budget_s: float = 8.0,
        sources: list[str] | None = None,
        auto_extend: bool = True,
    ) -> dict[str, Any]:
        before = self.table()
        weakest_before = self.weakest()
        runs: list[dict[str, Any]] = []
        for _ in range(max(1, iterations)):
            goal = self.weakest()
            cycle = self.engine.evolve(
                "planning and search",
                goal_type=goal,
                sources=sources,
                budget_s=budget_s,
                auto_extend=auto_extend,
                max_attempts=2,
            )
            runs.append(
                {
                    "goal": goal,
                    "ok": cycle.ok,
                    "plan": [step.capability for step in cycle.plan.steps],
                    "value": cycle.execution.get("value") if cycle.execution.get("ok") else None,
                    "extensions": cycle.extensions,
                }
            )
        after = self.table()
        return {
            "before": before,
            "after": after,
            "weakest_before": weakest_before,
            "weakest_after": self.weakest(),
            "runs": runs,
        }
