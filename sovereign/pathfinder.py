"""Planning as best-first search over capability types.

A state is the set of resource types currently available. A capability is an
operator that consumes some types and produces others. The search is A* with
an admissible heuristic (0 if the goal is present, else 1), deterministic
tie-breaking, and a failure memo: a start state that is *proven* to have no
route to a goal is recorded so later identical searches are pruned instantly.

This is classical search. It explores many routes and can run several goal
searches in parallel, but it is not quantum and claims no speedup beyond what
the hardware actually delivers.
"""

from __future__ import annotations

import heapq
import hashlib
import itertools
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .models import Capability, Plan, PlanStep
from .store import FabricStore


@dataclass(frozen=True)
class Operator:
    name: str
    inputs: frozenset[str]
    outputs: frozenset[str]
    version: int = 1


def operators_from(capabilities: list[Capability]) -> list[Operator]:
    ops = [
        Operator(
            name=cap.name,
            inputs=frozenset(cap.inputs),
            outputs=frozenset(cap.outputs),
            version=cap.version,
        )
        for cap in capabilities
    ]
    return sorted(ops, key=lambda op: (op.name, op.version))


class PathFinder:
    def __init__(self, store: FabricStore | None = None) -> None:
        self.store = store

    def plan(
        self,
        available: tuple[str, ...] | frozenset[str],
        goal: str,
        operators: list[Operator],
        max_expansions: int = 5000,
    ) -> Plan:
        start = frozenset(available)
        if goal in start:
            return Plan(goal=goal, steps=[], solved=True, reason="goal already available")

        memo_key = self._memo_key(goal, start, operators)
        if self.store is not None and self.store.memo_seen(memo_key):
            return Plan(
                goal=goal,
                steps=[],
                solved=False,
                reason="pruned: this start was previously proven to have no route",
            )

        counter = itertools.count()
        heap: list[tuple[int, int, int, frozenset[str], tuple[Operator, ...]]] = []

        def push(state: frozenset[str], cost: int, path: tuple[Operator, ...]) -> None:
            heuristic = 0 if goal in state else 1
            heapq.heappush(heap, (cost + heuristic, cost, next(counter), state, path))

        push(start, 0, ())
        best: dict[frozenset[str], int] = {start: 0}
        explored = 0
        exhausted = True

        while heap:
            if explored >= max_expansions:
                exhausted = False
                break
            _, cost, _, state, path = heapq.heappop(heap)
            if cost > best.get(state, cost + 1):
                continue
            if goal in state:
                steps = [
                    PlanStep(
                        capability=op.name,
                        consumes=tuple(sorted(op.inputs)),
                        produces=tuple(sorted(op.outputs)),
                        version=op.version,
                    )
                    for op in path
                ]
                return Plan(
                    goal=goal,
                    steps=steps,
                    solved=True,
                    explored=explored,
                    reason=f"route found in {len(steps)} step(s)",
                )
            explored += 1
            for op in operators:
                if not op.inputs <= state:
                    continue
                new_state = state | op.outputs
                if new_state == state:
                    continue
                new_cost = cost + 1
                if new_cost < best.get(new_state, new_cost + 1):
                    best[new_state] = new_cost
                    push(new_state, new_cost, path + (op,))

        reason = "no applicable route exists" if exhausted else "expansion budget exhausted"
        if self.store is not None and exhausted:
            self.store.memo_record(memo_key, reason)
        return Plan(goal=goal, steps=[], solved=False, explored=explored, reason=reason)

    def alternatives(
        self,
        available: tuple[str, ...] | frozenset[str],
        goal: str,
        operators: list[Operator],
        k: int = 3,
        max_expansions: int = 5000,
    ) -> list[Plan]:
        """Distinct routes, found by banning the last step of the previous one."""
        plans: list[Plan] = []
        seen: set[tuple[str, ...]] = set()
        banned: set[str] = set()
        for _ in range(max(1, k)):
            usable = [op for op in operators if op.name not in banned]
            plan = self.plan(available, goal, usable, max_expansions)
            if not plan.solved:
                break
            signature = tuple(step.capability for step in plan.steps)
            if signature in seen:
                break
            seen.add(signature)
            plans.append(plan)
            if not plan.steps:
                break
            banned.add(plan.steps[-1].capability)
        return plans

    def plan_many(
        self,
        available: tuple[str, ...] | frozenset[str],
        goals: list[str],
        operators: list[Operator],
        max_workers: int = 4,
    ) -> dict[str, Plan]:
        if not goals:
            return {}
        with ThreadPoolExecutor(max_workers=min(max_workers, len(goals))) as pool:
            results = list(
                pool.map(lambda g: self.plan(available, g, operators), goals)
            )
        return dict(zip(goals, results))

    @staticmethod
    def _memo_key(goal: str, start: frozenset[str], operators: list[Operator]) -> str:
        # A route is only "proven unsolvable" for a specific operator set, so the
        # world signature is part of the key. Registering a capability changes it.
        world = ";".join(
            f"{op.name}@{op.version}:{','.join(sorted(op.inputs))}>{','.join(sorted(op.outputs))}"
            for op in operators
        )
        signature = hashlib.sha1(world.encode("utf-8")).hexdigest()[:12]
        return f"plan:{goal}|{','.join(sorted(start))}|{signature}"
