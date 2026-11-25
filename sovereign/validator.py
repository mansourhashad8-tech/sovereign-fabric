"""The holistic validator: score an artifact against six criteria and refuse
to pass anything that overclaims.

Criteria (each scored 0..1):
  comprehensiveness  - how many consulted sources responded
  recency            - share of absorbed knowledge within the last 180 days
  constraint_transcendence - share of declared constraints actually handled
  determinism        - was the run reproducible by construction
  speed              - measured against a budget (unmeasured speed scores 0)
  guardianship       - were external sources actually reached

A claim with no evidence fails. Absolute or unfalsifiable language fails,
unless it is negated ("we do not claim quantum advantage"). This is the rule
that makes "never report failure" safe: the system may retry, but it may not
lie.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from .models import Evidence, ValidationReport

_OVERCLAIMS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"million[\s-]*(?:times|fold|x)\b", re.I), "million-fold speedup"),
    (re.compile(r"quantum\s+(?:advantage|supremacy|speedup)", re.I), "quantum advantage"),
    (re.compile(r"\bimpossible\b", re.I), "absolute impossibility"),
    (
        re.compile(
            r"\b(?:guaranteed|never\s+fails?|zero\s+failures?|no\s+failures?)\b", re.I
        ),
        "absolute reliability",
    ),
    (re.compile(r"\b100\s*%", re.I), "absolute reliability"),
    (re.compile(r"\bliving\s+(?:entity|being|organism)\b", re.I), "living-entity claim"),
    (re.compile(r"\binfinitely\s+(?:fast|scalable|capable)\b", re.I), "infinite capability"),
    (re.compile(r"\bzero[\s-](?:latency|cost)\b", re.I), "zero-resource claim"),
    (re.compile(r"\b(?:AGI|superintelligen\w*)\b", re.I), "AGI/superintelligence claim"),
    (
        re.compile(r"\b\d[\d,]{5,}\s*(?:x|times)\b", re.I),
        "numeric magnitude claim",
    ),
    (re.compile(r"orders?\s+of\s+magnitude", re.I), "order-of-magnitude claim"),
    (re.compile(r"\bself[\s-]?aware\b|\bconscious\b", re.I), "consciousness claim"),
    (
        re.compile(r"\b(?:never|always)\s+(?:wrong|right|correct|fails?)\b", re.I),
        "absolute correctness claim",
    ),
    (re.compile(r"\bperfect\s+solution\b", re.I), "perfect-solution claim"),
    (
        re.compile(r"\bno\s+limitations?\b|\bunlimited\s+power\b|\bliterally\s+infinite\b", re.I),
        "unbounded-capability claim",
    ),
]

_NEGATION = re.compile(
    r"\b(?:no|not|never|without|cannot|can't|isn't|aren't|doesn't|don't|won't|n't)\b",
    re.I,
)

_MIN_SCORE = 0.5


class HolisticValidator:
    def __init__(self, min_score: float = _MIN_SCORE) -> None:
        self.min_score = min_score

    def detect_overclaims(self, text: str) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        for pattern, label in _OVERCLAIMS:
            for match in pattern.finditer(text):
                if _negated(text, match.start()):
                    continue
                entry = f"{label}: '{match.group(0)}'"
                if entry in seen:
                    continue
                seen.add(entry)
                found.append(entry)
        return found

    def validate(
        self,
        subject: str,
        claims: list[str],
        evidence: list[Evidence],
        context: dict[str, Any] | None = None,
    ) -> ValidationReport:
        ctx = context or {}
        scores = {
            "comprehensiveness": _comprehensiveness(ctx),
            "recency": _ratio(ctx.get("fresh_units", 0), ctx.get("units_total", 0)),
            "constraint_transcendence": _constraints(ctx),
            "determinism": 1.0 if ctx.get("deterministic") else 0.0,
            "speed": _speed(ctx.get("duration_s"), ctx.get("budget_s")),
            "guardianship": 1.0 if ctx.get("external_sources_ok", 0) > 0 else 0.0,
        }

        failures: list[str] = []
        notes: list[str] = []

        overclaims = self.detect_overclaims(" ".join([subject, *claims]))
        if overclaims:
            failures.append(
                f"{len(overclaims)} overclaim(s) with no admissible evidence: "
                + "; ".join(overclaims)
            )

        if not evidence:
            failures.append("no evidence supplied")

        if claims and not evidence:
            failures.append("claims presented without evidence")

        for name, value in scores.items():
            if value < self.min_score:
                failures.append(f"{name} scored {value:.2f}, below threshold {self.min_score:.2f}")
                notes.append(_explain(name, value, ctx))

        return ValidationReport(
            subject=subject,
            scores=scores,
            passed=not failures,
            failures=failures,
            overclaims=overclaims,
            evidence=list(evidence),
            notes=notes,
        )

    @staticmethod
    def to_dict(report: ValidationReport) -> dict[str, Any]:
        return asdict(report)


def _negated(text: str, start: int) -> bool:
    window = text[max(0, start - 40) : start]
    return bool(_NEGATION.search(window))


def _ratio(numerator: Any, denominator: Any) -> float:
    try:
        denominator = float(denominator)
        if denominator <= 0:
            return 0.0
        return max(0.0, min(1.0, float(numerator) / denominator))
    except (TypeError, ValueError):
        return 0.0


def _comprehensiveness(ctx: dict[str, Any]) -> float:
    ok = int(ctx.get("sources_ok", 0) or 0)
    minimum = int(ctx.get("min_sources", 2) or 1)
    return max(0.0, min(1.0, ok / minimum))


def _constraints(ctx: dict[str, Any]) -> float:
    declared = int(ctx.get("constraints_declared", 0) or 0)
    if declared <= 0:
        return 0.5  # neutral: no constraints were declared, so none were transcended
    return _ratio(ctx.get("constraints_addressed", 0), declared)


def _speed(duration: Any, budget: Any) -> float:
    try:
        duration = float(duration)
        budget = float(budget)
    except (TypeError, ValueError):
        return 0.0  # unmeasured speed is not evidence of speed
    if duration <= 0:
        return 1.0
    return max(0.0, min(1.0, budget / duration))


def _explain(name: str, value: float, ctx: dict[str, Any]) -> str:
    if name == "guardianship":
        return "no external source was reached; only internal knowledge was used"
    if name == "speed":
        return (
            "speed was not measured against a budget"
            if ctx.get("duration_s") is None
            else f"run took {ctx.get('duration_s'):.3f}s against a {ctx.get('budget_s')}s budget"
        )
    if name == "recency":
        return "little or none of the absorbed knowledge is recent"
    if name == "comprehensiveness":
        return "too few consulted sources responded"
    return f"{name} did not meet the bar"
