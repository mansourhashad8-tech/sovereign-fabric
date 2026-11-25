"""Result-first execution protocol with mandatory escalating routes.

The protocol is deliberately narrow about what "verified" means. It runs a
fixed, bounded sequence of routes over the existing fabric and returns
``verified`` only when the six-criterion validator passes. When no route passes,
it returns ``escalation_required`` with the exact failed criteria and concrete
next actions. It never turns an unverified run into a success claim.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .evolution import EvolutionCycle, EvolutionEngine
from .intent import parse_intent

PROTOCOL = "sovereign-deterministic/v1"

BANNED_PHRASES: tuple[str, ...] = (
    "مستحيل",
    "لا يمكن",
    "غير متاح",
    "لا أعرف",
    "مش هقدر",
    "can't",
    "cannot",
    "impossible",
    "unavailable",
    "don't know",
)

_LANGUAGE_POLICY = (
    "State the verified result, the mechanism, and the evidence. When a route "
    "does not pass the validator, name the exact gap and the next executable "
    "action instead of declaring incapacity."
)


@dataclass(frozen=True)
class LanguageAudit:
    compliant: bool
    violations: list[dict[str, Any]] = field(default_factory=list)
    policy: str = _LANGUAGE_POLICY


@dataclass(frozen=True)
class Route:
    name: str
    description: str
    auto_extend: bool = False
    max_attempts: int = 1
    synthesize: dict[str, Any] | None = None


@dataclass
class RouteAttempt:
    name: str
    description: str
    ok: bool
    plan_solved: bool
    execution_ok: bool
    validator_passed: bool
    duration_s: float
    scores: dict[str, float]
    failures: list[str]
    steps: list[str]
    sources: list[str]
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_language(text: str) -> LanguageAudit:
    lowered = text.casefold()
    violations: list[dict[str, Any]] = []
    for phrase in BANNED_PHRASES:
        start = 0
        needle = phrase.casefold()
        while True:
            index = lowered.find(needle, start)
            if index < 0:
                break
            violations.append({"phrase": phrase, "index": index})
            start = index + len(needle)
    return LanguageAudit(compliant=not violations, violations=violations)


class DeterministicProtocol:
    def __init__(self, engine: EvolutionEngine, max_alternatives: int = 4) -> None:
        self.engine = engine
        self.max_alternatives = max(1, min(4, int(max_alternatives)))

    def routes(
        self,
        goal_type: str,
        initial: tuple[str, ...],
        synthesize: dict[str, Any] | None,
    ) -> list[Route]:
        routes = [
            Route(
                "direct",
                "current capability graph with one retrieval pass",
                max_attempts=1,
            ),
            Route(
                "broader_retrieval",
                "the same graph with a broader second retrieval query",
                max_attempts=2,
            ),
            Route(
                "autonomous_extension",
                "acquire or synthesize a missing blueprint, then re-plan",
                auto_extend=True,
                max_attempts=1,
            ),
        ]
        if synthesize is not None:
            routes.append(
                Route(
                    "supplied_synthesis",
                    "verified synthesis from the supplied specification",
                    auto_extend=True,
                    max_attempts=1,
                    synthesize=synthesize,
                )
            )
        return routes[: self.max_alternatives]

    def execute(
        self,
        request: str,
        *,
        goal_type: str | None = None,
        initial: tuple[str, ...] | None = None,
        text: str | None = None,
        sources: list[str] | None = None,
        synthesize: dict[str, Any] | None = None,
        budget_s: float = 5.0,
        max_alternatives: int | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        parsed = parse_intent(request)
        goal = goal_type or str(parsed["goal_type"])
        init = tuple(initial) if initial is not None else (str(parsed["initial"]),)
        payload = text if text is not None else str(parsed["text"])
        limit = self.max_alternatives if max_alternatives is None else max_alternatives
        routes = self.routes(goal, init, synthesize)[: max(1, min(4, int(limit)))]

        attempts: list[RouteAttempt] = []
        verified: RouteAttempt | None = None
        for route in routes:
            cycle = self.engine.evolve(
                request,
                goal_type=goal,
                initial=init,
                text=payload,
                sources=sources,
                synthesize=route.synthesize,
                budget_s=budget_s,
                auto_extend=route.auto_extend,
                max_attempts=route.max_attempts,
            )
            attempt = _attempt(route, cycle)
            attempts.append(attempt)
            if cycle.ok:
                verified = attempt
                break

        best = verified or max(attempts, key=_rank)
        report = self._report(
            request=request,
            goal=goal,
            initial=init,
            attempts=attempts,
            verified=verified,
            best=best,
            duration_s=time.monotonic() - started,
        )
        report["language_audit"] = asdict(audit_language(report["message"]))
        return report

    def _report(
        self,
        *,
        request: str,
        goal: str,
        initial: tuple[str, ...],
        attempts: list[RouteAttempt],
        verified: RouteAttempt | None,
        best: RouteAttempt,
        duration_s: float,
    ) -> dict[str, Any]:
        ok = verified is not None
        if ok:
            message = (
                f"تم تحقيق الهدف «{request}» عبر المسار «{best.name}» "
                f"بخطوات {best.steps} ومصادر {best.sources}، "
                f"واجتاز التحقق الكامل."
            )
            next_actions: list[str] = []
        else:
            gap = "; ".join(best.failures) or "the validator did not pass"
            message = (
                f"أُغلقت {len(attempts)} مسارات تنفيذية. أقوى مسار حالي هو "
                f"«{best.name}»؛ الفجوة الدقيقة: {gap}. "
                "الخطوة التالية المحددة مذكورة في next_actions."
            )
            next_actions = _next_actions(best, attempts)

        return {
            "protocol": PROTOCOL,
            "request": request,
            "status": "verified" if ok else "escalation_required",
            "verified": ok,
            "message": message,
            "result": best.value if ok else None,
            "mechanism": {
                "route": best.name,
                "description": best.description,
                "steps": best.steps,
                "sources": best.sources,
                "duration_s": round(duration_s, 4),
            },
            "evidence": {
                "validator_scores": best.scores,
                "failures": best.failures,
                "route_attempts": len(attempts),
            },
            "alternatives": [attempt.to_dict() for attempt in attempts],
            "final_validation": {
                "requested_goal": goal,
                "requested_initial": list(initial),
                "validator_passed": best.validator_passed,
                "execution_ok": best.execution_ok,
                "exact_match": bool(ok and best.validator_passed and best.execution_ok),
                "exact_match_basis": (
                    "goal-type match plus the six-criterion validator; this is not "
                    "a semantic proof of intent"
                ),
                "determinism_score": best.scores.get("determinism", 0.0),
                "freshness_score": best.scores.get("recency", 0.0),
                "freshness_window_days": 180,
                "guardianship_score": best.scores.get("guardianship", 0.0),
            },
            "next_actions": next_actions,
            "limits": [
                "verified means the six-criterion validator passed, not that the result is universally optimal",
                "the protocol tries bounded routes; it does not search an infinite space",
                "open-ended goals still require relevant sources or a synthesis specification",
            ],
        }


def _attempt(route: Route, cycle: EvolutionCycle) -> RouteAttempt:
    return RouteAttempt(
        name=route.name,
        description=route.description,
        ok=cycle.ok,
        plan_solved=cycle.plan.solved,
        execution_ok=bool(cycle.execution.get("ok")),
        validator_passed=cycle.validation.passed,
        duration_s=round(cycle.duration_s, 4),
        scores=dict(cycle.validation.scores),
        failures=list(cycle.validation.failures),
        steps=[step.capability for step in cycle.plan.steps],
        sources=list(cycle.consultation.ok_sources),
        value=cycle.execution.get("value") if cycle.ok else None,
    )


def _rank(attempt: RouteAttempt) -> tuple[int, int, float]:
    passed = sum(1 for value in attempt.scores.values() if value >= 0.5)
    return (1 if attempt.validator_passed else 0, passed, sum(attempt.scores.values()))


def _next_actions(best: RouteAttempt, attempts: list[RouteAttempt]) -> list[str]:
    actions: list[str] = []
    if best.scores.get("guardianship", 1) == 0:
        actions.append("provide an external source, API access, or a populated local corpus")
    if best.scores.get("comprehensiveness", 1) < 0.5:
        actions.append("add at least two responding knowledge sources")
    if best.scores.get("recency", 1) < 0.5:
        actions.append("retry with a broader or more recent query")
    if best.scores.get("speed", 1) < 0.5:
        actions.append("raise budget_s or reduce the requested work")
    if best.scores.get("constraint_transcendence", 1) < 0.5:
        actions.append("supply the missing synthesis or capability constraint")
    if not best.plan_solved:
        actions.append("supply a capability specification or examples for synthesis")
    if not actions:
        actions.append("rerun with the strongest route and inspect the validator failures")
    if len(attempts) < 4:
        actions.append("allow the remaining escalation routes")
    return actions
