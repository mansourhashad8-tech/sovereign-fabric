"""Capability blueprints and autonomous acquisition.

A blueprint is a behavioural specification: what a capability consumes,
what it produces, and a set of independent examples it must reproduce. When
planning is blocked, the system looks for a blueprint whose inputs are already
reachable and whose outputs add something new, then synthesises it through the
verification gate and re-plans. It chooses its own next capability; the gate
still decides whether it is admitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .capabilities import CapabilityRegistry
from .pathfinder import Operator, operators_from
from .synthesis import Synthesizer


@dataclass(frozen=True)
class Bprint:
    name: str
    description: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    spec: dict[str, Any]
    examples: tuple[tuple[dict[str, Any], dict[str, Any]], ...]


def _examples(*pairs: tuple[dict[str, Any], dict[str, Any]]) -> tuple:
    return tuple(pairs)


BLUEPRINTS: tuple[Bprint, ...] = (
    Bprint(
        name="text.upper",
        description="Uppercase a string",
        inputs=("text",),
        outputs=("upper",),
        spec={"op": "upper"},
        examples=_examples(
            ({"value": "abc"}, {"value": "ABC"}),
            ({"value": "Hello"}, {"value": "HELLO"}),
        ),
    ),
    Bprint(
        name="text.lower",
        description="Lowercase a string",
        inputs=("text",),
        outputs=("lower",),
        spec={"op": "lower"},
        examples=_examples(
            ({"value": "ABC"}, {"value": "abc"}),
            ({"value": "HeLLo"}, {"value": "hello"}),
        ),
    ),
    Bprint(
        name="text.reverse",
        description="Reverse a string",
        inputs=("text",),
        outputs=("reversed",),
        spec={"op": "reverse"},
        examples=_examples(
            ({"value": "abc"}, {"value": "cba"}),
            ({"value": ""}, {"value": ""}),
        ),
    ),
    Bprint(
        name="text.length",
        description="Length of a string",
        inputs=("text",),
        outputs=("length",),
        spec={"op": "length"},
        examples=_examples(
            ({"value": "abcd"}, {"value": 4}),
            ({"value": ""}, {"value": 0}),
        ),
    ),
    Bprint(
        name="text.double",
        description="Repeat a string twice",
        inputs=("text",),
        outputs=("doubled",),
        spec={
            "source": 'def run(payload):\n'
            '    value = payload.get("value", "")\n'
            '    return {"value": value + value}\n'
        },
        examples=_examples(
            ({"value": "ab"}, {"value": "abab"}),
            ({"value": "x"}, {"value": "xx"}),
        ),
    ),
    Bprint(
        name="list.total",
        description="Sum a list of numbers",
        inputs=("numbers",),
        outputs=("total",),
        spec={"op": "sum_list"},
        examples=_examples(
            ({"value": [1, 2, 3]}, {"value": 6}),
            ({"value": []}, {"value": 0}),
        ),
    ),
    Bprint(
        name="text.heading",
        description="Render text as a markdown heading",
        inputs=("text",),
        outputs=("markdown",),
        spec={
            "source": 'def run(payload):\n'
            '    return {"value": "## " + str(payload.get("value", ""))}\n'
        },
        examples=_examples(
            ({"value": "hi"}, {"value": "## hi"}),
            ({"value": ""}, {"value": "## "}),
        ),
    ),
)


def _reachable(initial: tuple[str, ...], ops: list[Operator]) -> set[str]:
    reach = set(initial)
    changed = True
    while changed:
        changed = False
        for op in ops:
            if op.inputs <= reach and not op.outputs <= reach:
                reach |= set(op.outputs)
                changed = True
    return reach


def autonomous_extend(
    registry: CapabilityRegistry,
    synthesizer: Synthesizer,
    pathfinder,
    initial: tuple[str, ...],
    goal: str,
    blueprints=None,
    max_additions: int = 3,
) -> tuple:
    library = BLUEPRINTS if blueprints is None else tuple(blueprints)
    added: list[str] = []
    attempts: list[dict[str, Any]] = []

    for _ in range(max_additions):
        ops = operators_from(registry.list_active())
        plan = pathfinder.plan(initial, goal, ops)
        if plan.solved:
            return plan, added, attempts

        reach = _reachable(initial, ops)
        candidates = [
            bp
            for bp in library
            if registry.get(bp.name) is None
            and set(bp.inputs) <= reach
            and not set(bp.outputs) <= reach
        ]
        if not candidates:
            break

        candidates.sort(
            key=lambda bp: (
                goal not in bp.outputs,
                -len(set(bp.outputs) - reach),
                bp.name,
            )
        )
        bp = candidates[0]
        result = synthesizer.synthesize(
            name=bp.name,
            description=bp.description,
            inputs=bp.inputs,
            outputs=bp.outputs,
            spec=dict(bp.spec),
            examples=list(bp.examples),
        )
        attempts.append(
            {"blueprint": bp.name, "admitted": result.admitted, "reason": result.reason}
        )
        if result.admitted:
            added.append(bp.name)

    ops = operators_from(registry.list_active())
    plan = pathfinder.plan(initial, goal, ops)
    return plan, added, attempts
