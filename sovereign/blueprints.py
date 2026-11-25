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
        name="text.tokens",
        description="Split text into whitespace tokens",
        inputs=("text",),
        outputs=("list",),
        spec={"source": 'def run(payload):\n    return {"value": str(payload.get("value", "")).split()}\n'},
        examples=_examples(
            ({"value": "a b c"}, {"value": ["a", "b", "c"]}),
            ({"value": ""}, {"value": []}),
        ),
    ),
    Bprint(
        name="text.numbers",
        description="Parse whitespace or comma separated numbers",
        inputs=("text",),
        outputs=("numbers",),
        spec={
            "source": 'def run(payload):\n'
            '    parts = str(payload.get("value", "")).replace(",", " ").split()\n'
            '    return {"value": [float(part) if "." in part else int(part) for part in parts]}\n'
        },
        examples=_examples(
            ({"value": "1 2 3"}, {"value": [1, 2, 3]}),
            ({"value": "1.5,2"}, {"value": [1.5, 2]}),
        ),
    ),
    Bprint(
        name="text.json",
        description="Parse a JSON string into a value",
        inputs=("text",),
        outputs=("json",),
        spec={
            "source": 'import json\n'
            'def run(payload):\n'
            '    value = payload.get("value", "{}")\n'
            '    if isinstance(value, str):\n'
            '        value = json.loads(value)\n'
            '    return {"value": value}\n'
        },
        examples=_examples(
            ({"value": '{"a": 1}'}, {"value": {"a": 1}}),
            ({"value": "[]"}, {"value": []}),
        ),
    ),
    Bprint(
        name="text.arabic_normalized",
        description="Normalize Arabic diacritics and letter variants",
        inputs=("text",),
        outputs=("arabic",),
        spec={
            "source": 'import re\n'
            'def run(payload):\n'
            '    value = str(payload.get("value", ""))\n'
            '    value = re.sub(r"[\\u0610-\\u061a\\u064b-\\u065f\\u0670\\u06d6-\\u06ed\\u0640]", "", value)\n'
            '    for source, target in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ؤ", "و"), ("ئ", "ي"), ("ة", "ه")):\n'
            '        value = value.replace(source, target)\n'
            '    return {"value": value}\n'
        },
        examples=_examples(
            ({"value": "أَكْتُبُ"}, {"value": "اكتب"}),
            ({"value": "مَدْرَسَة"}, {"value": "مدرسه"}),
        ),
    ),
    Bprint(
        name="text.arabic_words",
        description="Extract Arabic words after normalization",
        inputs=("text",),
        outputs=("words",),
        spec={
            "source": 'import re\n'
            'def run(payload):\n'
            '    value = str(payload.get("value", ""))\n'
            '    value = re.sub(r"[\\u0610-\\u061a\\u064b-\\u065f\\u0670\\u06d6-\\u06ed\\u0640]", "", value)\n'
            '    for source, target in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ؤ", "و"), ("ئ", "ي"), ("ة", "ه")):\n'
            '        value = value.replace(source, target)\n'
            '    return {"value": re.findall(r"[\\u0600-\\u06ff]+", value)}\n'
        },
        examples=_examples(
            ({"value": "الكتابُ الجديد"}, {"value": ["الكتاب", "الجديد"]}),
            ({"value": "123"}, {"value": []}),
        ),
    ),
    Bprint(
        name="text.slug",
        description="Turn text into a lowercase URL slug",
        inputs=("text",),
        outputs=("slug",),
        spec={
            "source": 'import re\n'
            'def run(payload):\n'
            '    value = str(payload.get("value", "")).strip().lower()\n'
            '    value = re.sub(r"[^\\w\\s-]", "", value, flags=re.UNICODE)\n'
            '    value = re.sub(r"[\\s_-]+", "-", value).strip("-")\n'
            '    return {"value": value}\n'
        },
        examples=_examples(
            ({"value": "Hello, World!"}, {"value": "hello-world"}),
            ({"value": "  A  B  "}, {"value": "a-b"}),
        ),
    ),
    Bprint(
        name="text.title",
        description="Title-case a string",
        inputs=("text",),
        outputs=("title",),
        spec={"source": 'def run(payload):\n    return {"value": str(payload.get("value", "")).title()}\n'},
        examples=_examples(
            ({"value": "hello world"}, {"value": "Hello World"}),
            ({"value": ""}, {"value": ""}),
        ),
    ),
    Bprint(
        name="list.unique",
        description="Keep the first occurrence of each list item",
        inputs=("list",),
        outputs=("unique",),
        spec={
            "source": 'def run(payload):\n'
            '    seen = []\n'
            '    for item in payload.get("value", []):\n'
            '        if item not in seen:\n'
            '            seen.append(item)\n'
            '    return {"value": seen}\n'
        },
        examples=_examples(
            ({"value": [1, 2, 1, 3]}, {"value": [1, 2, 3]}),
            ({"value": []}, {"value": []}),
        ),
    ),
    Bprint(
        name="list.sorted",
        description="Sort a list",
        inputs=("list",),
        outputs=("sorted",),
        spec={"source": 'def run(payload):\n    return {"value": sorted(payload.get("value", []))}\n'},
        examples=_examples(
            ({"value": [3, 1, 2]}, {"value": [1, 2, 3]}),
            ({"value": []}, {"value": []}),
        ),
    ),
    Bprint(
        name="list.mean",
        description="Arithmetic mean of a numeric list",
        inputs=("numbers",),
        outputs=("mean",),
        spec={
            "source": 'def run(payload):\n'
            '    values = list(payload.get("value", []))\n'
            '    return {"value": (sum(values) / len(values)) if values else 0}\n'
        },
        examples=_examples(
            ({"value": [1, 2, 3]}, {"value": 2.0}),
            ({"value": []}, {"value": 0}),
        ),
    ),
    Bprint(
        name="list.median",
        description="Median of a numeric list",
        inputs=("numbers",),
        outputs=("median",),
        spec={
            "source": 'def run(payload):\n'
            '    values = sorted(payload.get("value", []))\n'
            '    if not values:\n'
            '        return {"value": 0}\n'
            '    middle = len(values) // 2\n'
            '    if len(values) % 2:\n'
            '        return {"value": values[middle]}\n'
            '    return {"value": (values[middle - 1] + values[middle]) / 2}\n'
        },
        examples=_examples(
            ({"value": [3, 1, 2]}, {"value": 2}),
            ({"value": [1, 2, 3, 4]}, {"value": 2.5}),
        ),
    ),
    Bprint(
        name="json.keys",
        description="List object keys",
        inputs=("json",),
        outputs=("keys",),
        spec={"source": 'def run(payload):\n    return {"value": list(dict(payload.get("value", {})).keys())}\n'},
        examples=_examples(
            ({"value": {"a": 1, "b": 2}}, {"value": ["a", "b"]}),
            ({"value": {}}, {"value": []}),
        ),
    ),
    Bprint(
        name="json.flatten",
        description="Flatten a nested JSON object with dotted paths",
        inputs=("json",),
        outputs=("flat",),
        spec={
            "source": 'def run(payload):\n'
            '    def walk(value, prefix):\n'
            '        out = {}\n'
            '        if isinstance(value, dict):\n'
            '            for key, item in value.items():\n'
            '                name = f"{prefix}.{key}" if prefix else str(key)\n'
            '                out.update(walk(item, name))\n'
            '        elif isinstance(value, list):\n'
            '            for index, item in enumerate(value):\n'
            '                out.update(walk(item, f"{prefix}[{index}]"))\n'
            '        else:\n'
            '            out[prefix] = value\n'
            '        return out\n'
            '    return {"value": walk(payload.get("value", {}), "")}\n'
        },
        examples=_examples(
            ({"value": {"a": {"b": 1}, "c": [2]}}, {"value": {"a.b": 1, "c[0]": 2}}),
            ({"value": {}}, {"value": {}}),
        ),
    ),
    Bprint(
        name="text.sha256",
        description="SHA-256 hex digest of a string",
        inputs=("text",),
        outputs=("digest",),
        spec={
            "source": 'import hashlib\n'
            'def run(payload):\n'
            '    value = str(payload.get("value", "")).encode("utf-8")\n'
            '    return {"value": hashlib.sha256(value).hexdigest()}\n'
        },
        examples=_examples(
            ({"value": "abc"}, {"value": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"}),
        ),
    ),
    Bprint(
        name="text.base64",
        description="Base64-encode UTF-8 text",
        inputs=("text",),
        outputs=("base64",),
        spec={
            "source": 'import base64\n'
            'def run(payload):\n'
            '    value = str(payload.get("value", "")).encode("utf-8")\n'
            '    return {"value": base64.b64encode(value).decode("ascii")}\n'
        },
        examples=_examples(
            ({"value": "hello"}, {"value": "aGVsbG8="}),
            ({"value": ""}, {"value": ""}),
        ),
    ),
    Bprint(
        name="text.truncate",
        description="Truncate a string to a bounded length",
        inputs=("text",),
        outputs=("truncated",),
        spec={
            "source": 'def run(payload):\n'
            '    value = str(payload.get("value", ""))\n'
            '    limit = int(payload.get("limit", 20))\n'
            '    return {"value": value[:max(0, limit)]}\n'
        },
        examples=_examples(
            ({"value": "abcdef", "limit": 3}, {"value": "abc"}),
            ({"value": "abc", "limit": 10}, {"value": "abc"}),
        ),
    ),
    Bprint(
        name="text.word_count",
        description="Count whitespace-separated words",
        inputs=("text",),
        outputs=("word_count",),
        spec={"source": 'def run(payload):\n    return {"value": len(str(payload.get("value", "")).split())}\n'},
        examples=_examples(
            ({"value": "one two three"}, {"value": 3}),
            ({"value": ""}, {"value": 0}),
        ),
    ),
    Bprint(
        name="list.chunk",
        description="Split a list into bounded chunks",
        inputs=("list",),
        outputs=("chunks",),
        spec={
            "source": 'def run(payload):\n'
            '    values = list(payload.get("value", []))\n'
            '    size = max(1, int(payload.get("size", 2)))\n'
            '    return {"value": [values[i:i + size] for i in range(0, len(values), size)]}\n'
        },
        examples=_examples(
            ({"value": [1, 2, 3, 4, 5], "size": 2}, {"value": [[1, 2], [3, 4], [5]]}),
            ({"value": [], "size": 2}, {"value": []}),
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
    acquirer=None,
) -> tuple:
    library = BLUEPRINTS if blueprints is None else tuple(blueprints)
    added: list[str] = []
    attempts: list[dict[str, Any]] = []
    tried: set[str] = set()

    for _ in range(max_additions):
        ops = operators_from(registry.list_active())
        plan = pathfinder.plan(initial, goal, ops)
        if plan.solved:
            return plan, added, attempts

        reach = _reachable(initial, ops)
        candidates = [
            bp
            for bp in library
            if bp.name not in tried
            and registry.get(bp.name) is None
            and set(bp.inputs) <= reach
            and not set(bp.outputs) <= reach
        ]
        if not candidates:
            break

        def goal_distance(bp: Bprint) -> int:
            if goal in bp.outputs:
                return 0
            for other in library:
                if goal in other.outputs and set(other.inputs) & set(bp.outputs):
                    return 1
            return 2

        candidates.sort(
            key=lambda bp: (
                goal_distance(bp),
                -len(set(bp.outputs) - reach),
                bp.name,
            )
        )
        bp = candidates[0]
        tried.add(bp.name)
        result = synthesizer.synthesize(
            name=bp.name,
            description=bp.description,
            inputs=bp.inputs,
            outputs=bp.outputs,
            spec=dict(bp.spec),
            examples=list(bp.examples),
        )
        attempts.append(
            {
                "blueprint": bp.name,
                "origin": "template",
                "admitted": result.admitted,
                "reason": result.reason,
            }
        )
        admitted = result.admitted
        if not admitted and acquirer is not None:
            acquired = acquirer.acquire(
                bp.name, bp.description, bp.inputs, bp.outputs, list(bp.examples)
            )
            attempts.append(
                {
                    "blueprint": bp.name,
                    "origin": "expert",
                    "admitted": acquired.admitted,
                    "reason": acquired.reason,
                    "tried": len(acquired.attempts),
                }
            )
            admitted = acquired.admitted
        if admitted:
            added.append(bp.name)

    ops = operators_from(registry.list_active())
    plan = pathfinder.plan(initial, goal, ops)
    return plan, added, attempts
