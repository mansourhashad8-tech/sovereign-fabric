"""Self-directed practice: generate tasks from the system's own knowledge.

This is the closest honest thing to "continuous self-evolution": the system
picks concepts it has absorbed, forms small tasks around them, attempts each
task with its own planner and gate, and records the outcome. It is a bounded
practice loop, not curiosity and not consciousness.
"""

from __future__ import annotations

from dataclasses import dataclass

from .absorption import absorb

_GOALS = ("markdown", "upper", "length", "doubled", "lower", "summary")


@dataclass
class PracticeTask:
    request: str
    goal_type: str
    text: str


class Curriculum:
    def __init__(self, engine) -> None:
        self.engine = engine

    def propose(self, k: int = 3) -> list[PracticeTask]:
        units = self.engine.store.list_knowledge(limit=max(k, 1) * 2)
        tasks: list[PracticeTask] = []
        for index, unit in enumerate(units[:k]):
            goal = _GOALS[index % len(_GOALS)]
            text = unit.summary or unit.title
            tasks.append(PracticeTask(f"practise {goal} on: {unit.title}", goal, text))
        return tasks

    def run(
        self,
        iterations: int = 3,
        sources: list[str] | None = None,
        budget_s: float = 10.0,
        auto_extend: bool = True,
    ) -> list[dict]:
        if self.engine.store.count_knowledge() == 0:
            seed = self.engine.guardians.consult("planning search engineering", limit=5)
            absorb(self.engine.store, seed.units)

        results: list[dict] = []
        for task in self.propose(iterations):
            cycle = self.engine.evolve(
                task.request,
                goal_type=task.goal_type,
                initial=("text",),
                text=task.text,
                sources=sources,
                budget_s=budget_s,
                auto_extend=auto_extend,
            )
            results.append(
                {
                    "request": task.request,
                    "goal_type": task.goal_type,
                    "ok": cycle.ok,
                    "plan": [step.capability for step in cycle.plan.steps],
                    "result": cycle.execution.get("value")
                    if cycle.execution.get("ok")
                    else None,
                    "passed": cycle.validation.passed,
                }
            )
        return results
