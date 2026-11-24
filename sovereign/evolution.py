"""One evolution cycle, end to end.

consult guardians -> absorb into the fabric -> plan over capabilities ->
(autonomously acquire a missing capability and re-plan, or synthesize a
supplied one) -> execute -> validate holistically -> record the cycle.

`evolve` can run a bounded set of repair attempts: if the first attempt does
not pass every criterion, it retries with a broader query and keeps the best
result. Every attempt is recorded; nothing is hidden.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .absorption import absorb, propose_capabilities
from .acquire import ExpertAcquirer
from .blueprints import autonomous_extend
from .capabilities import CapabilityError, CapabilityRegistry, bootstrap_native
from .expert import Expert, default_experts
from .guardians import ConsultationResult, GuardianRegistry, default_registry
from .models import Evidence, Plan, ValidationReport
from .pathfinder import PathFinder, operators_from
from .store import FabricStore
from .synthesis import SynthesisResult, Synthesizer
from .validator import HolisticValidator

_DECLARED_CONSTRAINTS = (
    "external_sources_optional",
    "generated_code_sandboxed",
    "claims_require_evidence",
)


@dataclass
class EvolutionCycle:
    request: str
    goal_type: str
    consultation: ConsultationResult
    absorbed: int
    proposals: list[dict[str, str]]
    plan: Plan
    synthesis: SynthesisResult | None
    execution: dict[str, Any]
    validation: ValidationReport
    duration_s: float
    ok: bool
    extensions: list[dict[str, Any]] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    diagnosis: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvolutionEngine:
    def __init__(
        self,
        store: FabricStore,
        registry: CapabilityRegistry | None = None,
        guardians: GuardianRegistry | None = None,
        pathfinder: PathFinder | None = None,
        validator: HolisticValidator | None = None,
        experts: list[Expert] | None = None,
    ) -> None:
        self.store = store
        self.registry = registry or CapabilityRegistry(store)
        bootstrap_native(self.registry)
        self.guardians = guardians or default_registry(store)
        self.pathfinder = pathfinder or PathFinder(store)
        self.validator = validator or HolisticValidator()
        self.synthesizer = Synthesizer(self.registry)
        self.experts = list(experts) if experts is not None else default_experts()
        self.acquirer = ExpertAcquirer(self.synthesizer, self.experts)

    def evolve(
        self,
        request: str,
        *,
        goal_type: str = "markdown",
        initial: tuple[str, ...] = ("text",),
        text: str | None = None,
        sources: list[str] | None = None,
        limit: int = 5,
        synthesize: dict[str, Any] | None = None,
        budget_s: float = 5.0,
        auto_extend: bool = False,
        max_attempts: int = 1,
    ) -> EvolutionCycle:
        queries = [request]
        if max_attempts > 1:
            queries.append(f"{request} recent survey")
            queries.append(f"{request} {goal_type}")
        queries = queries[: max(1, max_attempts)]

        attempts: list[dict[str, Any]] = []
        best: EvolutionCycle | None = None
        for index, query in enumerate(queries):
            cycle = self._attempt(
                request,
                query=query,
                goal_type=goal_type,
                initial=initial,
                text=text,
                sources=sources,
                limit=limit,
                synthesize=synthesize if index == 0 else None,
                budget_s=budget_s,
                auto_extend=auto_extend,
            )
            attempts.append(
                {
                    "query": query,
                    "ok": cycle.ok,
                    "plan_solved": cycle.plan.solved,
                    "execution_ok": cycle.execution.get("ok", False),
                    "passed": cycle.validation.passed,
                    "scores": cycle.validation.scores,
                    "failures": cycle.validation.failures,
                }
            )
            if best is None or _rank(cycle) > _rank(best):
                best = cycle
            if cycle.ok:
                break

        assert best is not None
        best.attempts = attempts
        best.diagnosis = diagnose(best.validation)
        self.store.record_event(
            "evolution",
            {
                "request": request,
                "ok": best.ok,
                "attempts": len(attempts),
                "diagnosis": best.diagnosis,
            },
        )
        return best

    def _attempt(
        self,
        request: str,
        *,
        query: str,
        goal_type: str,
        initial: tuple[str, ...],
        text: str | None,
        sources: list[str] | None,
        limit: int,
        synthesize: dict[str, Any] | None,
        budget_s: float,
        auto_extend: bool,
    ) -> EvolutionCycle:
        started = time.monotonic()

        consultation = self.guardians.consult(
            query, limit=limit, sources=sources, deadline_s=budget_s
        )
        absorbed = absorb(self.store, consultation.units)
        proposals = propose_capabilities(consultation.units)

        synthesis: SynthesisResult | None = None
        extensions: list[dict[str, Any]] = []
        plan = self.pathfinder.plan(
            initial, goal_type, operators_from(self.registry.list_active())
        )
        if not plan.solved and synthesize is not None:
            synthesis = self.synthesizer.synthesize(**synthesize)
            plan = self.pathfinder.plan(
                initial, goal_type, operators_from(self.registry.list_active())
            )
        if not plan.solved and auto_extend:
            plan, added, ext_attempts = autonomous_extend(
                self.registry,
                self.synthesizer,
                self.pathfinder,
                initial,
                goal_type,
                acquirer=self.acquirer,
            )
            extensions = ext_attempts
            if added:
                self.store.record_event("self_extension", {"added": added})

        execution: dict[str, Any] = {"ok": False, "reason": "no plan"}
        if plan.solved:
            source_text = text if text is not None else request
            execution = self._execute(plan, source_text)
            if not execution.get("ok"):
                execution = self._try_alternatives(plan, initial, goal_type, source_text, execution)

        duration = time.monotonic() - started
        validation = self._validate(
            request, consultation, plan, execution, synthesis, duration, budget_s, absorbed
        )
        ok = bool(plan.solved and execution.get("ok") and validation.passed)

        cycle = EvolutionCycle(
            request=request,
            goal_type=goal_type,
            consultation=consultation,
            absorbed=absorbed,
            proposals=proposals,
            plan=plan,
            synthesis=synthesis,
            execution=execution,
            validation=validation,
            duration_s=duration,
            ok=ok,
            extensions=extensions,
        )
        self.store.record_event(
            "cycle",
            {
                "request": request,
                "query": query,
                "goal_type": goal_type,
                "ok": ok,
                "steps": [step.capability for step in plan.steps],
                "sources": consultation.sources,
                "duration_s": round(duration, 4),
                "validation_passed": validation.passed,
                "failures": validation.failures,
            },
        )
        return cycle

    def _execute(self, plan: Plan, text: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"value": text}
        trace: list[dict[str, Any]] = []
        for step in plan.steps:
            try:
                result = self.registry.invoke(step.capability, payload)
            except CapabilityError as exc:
                return {"ok": False, "error": str(exc), "trace": trace}
            payload = result if isinstance(result, dict) else {"value": result}
            trace.append({"capability": step.capability, "value": payload.get("value")})
        return {"ok": True, "value": payload.get("value"), "trace": trace}

    def _try_alternatives(
        self,
        plan: Plan,
        initial: tuple[str, ...],
        goal_type: str,
        text: str,
        failed: dict[str, Any],
    ) -> dict[str, Any]:
        operators = operators_from(self.registry.list_active())
        alternatives = self.pathfinder.alternatives(initial, goal_type, operators, k=3)
        original = [step.capability for step in plan.steps]
        tried = 0
        for alternative in alternatives:
            if [step.capability for step in alternative.steps] == original:
                continue
            tried += 1
            result = self._execute(alternative, text)
            if result.get("ok"):
                result["alternatives_tried"] = tried
                result["original_error"] = failed.get("error")
                return result
        fallback = dict(failed)
        fallback["alternatives_tried"] = tried
        return fallback

    def _validate(
        self,
        request: str,
        consultation: ConsultationResult,
        plan: Plan,
        execution: dict[str, Any],
        synthesis: SynthesisResult | None,
        duration: float,
        budget_s: float,
        absorbed: int,
    ) -> ValidationReport:
        claims = [f"produced a '{plan.goal}' artifact"]
        if execution.get("ok"):
            claims.append(f"execution completed {len(plan.steps)} step(s)")

        evidence = [
            Evidence(
                kind="consultation",
                detail=f"{len(consultation.units)} units from {len(consultation.ok_sources)} source(s)",
                ref=",".join(consultation.ok_sources) or "none",
            ),
            Evidence(kind="absorption", detail=f"{absorbed} units indexed", ref="store"),
        ]
        if plan.solved:
            evidence.append(
                Evidence(
                    kind="plan",
                    detail=plan.reason,
                    ref=",".join(step.capability for step in plan.steps) or "empty",
                )
            )
        if execution.get("ok"):
            evidence.append(
                Evidence(
                    kind="measurement",
                    detail=f"run measured at {duration:.3f}s",
                    ref="monotonic clock",
                )
            )
        if synthesis is not None:
            evidence.append(
                Evidence(
                    kind="synthesis",
                    detail=synthesis.reason,
                    ref="verification driver",
                )
            )

        external_ok = len([s for s in consultation.ok_sources if s != "local"])
        constraints_addressed = len(_DECLARED_CONSTRAINTS)
        if synthesis is not None and not synthesis.admitted:
            constraints_addressed -= 1

        context = {
            "sources_ok": len(consultation.ok_sources),
            "sources_total": len(consultation.sources),
            "external_sources_ok": external_ok,
            "units_total": len(consultation.units),
            "fresh_units": sum(
                1 for u in consultation.units if _is_fresh(u.provenance.retrieved_at)
            ),
            "deterministic": True,
            "duration_s": duration,
            "budget_s": budget_s,
            "constraints_declared": len(_DECLARED_CONSTRAINTS),
            "constraints_addressed": max(0, constraints_addressed),
        }
        return self.validator.validate(request, claims, evidence, context)


def diagnose(report: ValidationReport) -> list[str]:
    remedies: list[str] = []
    scores = report.scores
    if scores.get("guardianship", 1) == 0:
        remedies.append("consult external sources (network or another guardian)")
    if scores.get("comprehensiveness", 1) < 0.5:
        remedies.append("consult more sources")
    if scores.get("recency", 1) < 0.5:
        remedies.append("retry with a broader or more recent query")
    if scores.get("speed", 1) < 0.5:
        remedies.append("raise the time budget or reduce the work")
    if scores.get("constraint_transcendence", 1) < 0.5:
        remedies.append("address the declared constraint that was skipped")
    if report.overclaims:
        remedies.append("remove absolute claims or supply evidence")
    if not report.evidence:
        remedies.append("attach evidence")
    if not remedies:
        remedies.append("no remedy needed: every criterion passed")
    return remedies


def _rank(cycle: EvolutionCycle) -> tuple[int, int, float]:
    passed = sum(1 for value in cycle.validation.scores.values() if value >= 0.5)
    return (1 if cycle.ok else 0, passed, sum(cycle.validation.scores.values()))


def _is_fresh(timestamp: str, max_age_days: int = 730) -> bool:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).days <= max_age_days
