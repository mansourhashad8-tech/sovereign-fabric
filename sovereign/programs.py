"""Enumerative program synthesis over a small, pure expression language.

The search is deliberately narrow: string and number transformations built
from whitelisted operations. Candidates are evaluated in-process against the
examples as a cheap filter, then the first fit is verified again inside the
isolated gate. A program is admitted only if it reproduces every example.

This is not general program synthesis. The examples are the specification, so
a program that fits them can still be wrong about unseen inputs. The gate makes
the claim precise: "reproduces these examples", not "is correct".
"""

from __future__ import annotations

from typing import Any, Iterator

_SAFE = {
    "abs": abs,
    "all": all,
    "any": any,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "reversed": reversed,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
}

_IDENTITY = [("identity", "value")]

_STRING = [
    ("lowercase", "value.lower()"),
    ("uppercase", "value.upper()"),
    ("title case", "value.title()"),
    ("capitalized", "value.capitalize()"),
    ("trimmed", "value.strip()"),
    ("characters reversed", "value[::-1]"),
    ("whitespace squashed", '" ".join(value.split())'),
    ("slug", '"-".join(value.lower().split())'),
    ("underscored", '"_".join(value.lower().split())'),
    ("spaces removed", 'value.replace(" ", "")'),
    ("underscores to spaces", 'value.replace("_", " ")'),
    ("dashes to spaces", 'value.replace("-", " ")'),
    ("spaces to underscores", 'value.replace(" ", "_")'),
    ("words reversed", '" ".join(reversed(value.split()))'),
    ("initials", '"".join(w[0] for w in value.split() if w)'),
    ("vowels removed", '"".join(ch for ch in value if ch.lower() not in "aeiou")'),
    ("case swapped", "value.swapcase()"),
    ("word count", "len(value.split())"),
    ("character count", "len(value)"),
    ("first word", "value.split()[0]"),
    ("last word", "value.split()[-1]"),
    ("title words", '" ".join(w.capitalize() for w in value.split())'),
    ("upper words", '" ".join(w.upper() for w in value.split())'),
    ("sorted words", '" ".join(sorted(value.split()))'),
    ("unique words", '" ".join(sorted(set(value.split())))'),
]

_STRING_WRAPPERS = [
    ("lowercased", "({}).lower()"),
    ("uppercased", "({}).upper()"),
    ("trimmed", "({}).strip()"),
    ("whitespace squashed", '" ".join(({}).split())'),
    ("spaces removed", '"".join(({}).split())'),
    ("characters reversed", "({})[::-1]"),
    ("hyphenated", '"-".join(({}).split())'),
    ("words reversed", '" ".join(reversed(({}).split()))'),
]

_LIST = [
    ("sum", "sum(value)"),
    ("count", "len(value)"),
    ("maximum", "max(value)"),
    ("minimum", "min(value)"),
    ("mean", "sum(value) / len(value)"),
    ("sorted ascending", "sorted(value)"),
    ("sorted descending", "sorted(value, reverse=True)"),
    ("doubled", "[x * 2 for x in value]"),
    ("incremented", "[x + 1 for x in value]"),
    ("squared", "[x * x for x in value]"),
    ("positives", "[x for x in value if x > 0]"),
    ("sum of squares", "sum(x * x for x in value)"),
    ("range", "max(value) - min(value)"),
    ("distinct sorted", "sorted(set(value))"),
]

_LIST_WRAPPERS = [
    ("summed", "sum({})"),
    ("counted", "len({})"),
    ("maximized", "max({})"),
    ("minimized", "min({})"),
    ("sorted", "sorted({})"),
]

_SCALAR = [
    ("doubled", "value * 2"),
    ("incremented", "value + 1"),
    ("decremented", "value - 1"),
    ("squared", "value * value"),
    ("absolute", "abs(value)"),
    ("negated", "-value"),
    ("last digit", "value % 10"),
    ("as integer", "int(value)"),
    ("as float", "float(value)"),
    ("as text", "str(value)"),
]


def _source(expression: str) -> str:
    return (
        "def run(payload):\n"
        '    value = payload.get("value")\n'
        f'    return {{"value": {expression}}}\n'
    )


def _evaluate(expression: str, value: Any) -> Any:
    return eval(expression, {"__builtins__": {}, **_SAFE, "value": value})


class ProgramSearch:
    def __init__(self, max_depth: int = 2) -> None:
        self.max_depth = max_depth

    def _base(self, value: Any) -> list[tuple[str, str]]:
        if isinstance(value, str):
            return _IDENTITY + _STRING
        if isinstance(value, list):
            return _IDENTITY + _LIST
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return _IDENTITY + _SCALAR
        return _IDENTITY + [("as text", "str(value)")]

    def _wrappers(self, value: Any) -> list[tuple[str, str]]:
        if isinstance(value, str):
            return _STRING_WRAPPERS
        if isinstance(value, list):
            return _LIST_WRAPPERS
        return []

    def candidates(self, value: Any) -> Iterator[tuple[str, str]]:
        seen: set[str] = set()
        base = self._base(value)
        for label, expression in base:
            if expression not in seen:
                seen.add(expression)
                yield label, expression
        if self.max_depth < 2:
            return
        for label, expression in base:
            for wrap_label, wrapper in self._wrappers(value):
                composed = wrapper.format(expression)
                if composed in seen:
                    continue
                seen.add(composed)
                yield f"{wrap_label} {label}", composed

    def fits(self, expression: str, values: list[Any], expected: list[Any]) -> bool:
        for value, want in zip(values, expected):
            try:
                if _evaluate(expression, value) != want:
                    return False
            except Exception:
                return False
        return True

    def find(self, pairs: list[Any]) -> tuple[str, str] | None:
        if not pairs:
            return None
        values = [dict(given).get("value") for given, _ in pairs]
        expected = [dict(want).get("value") for _, want in pairs]
        for label, expression in self.candidates(values[0]):
            if self.fits(expression, values, expected):
                return _source(expression), label
        return None
