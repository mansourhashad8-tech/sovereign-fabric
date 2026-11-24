"""One evolution cycle, end to end.

consult guardians -> absorb into the fabric -> plan over capabilities ->
(optionally synthesize a missing capability and replan) -> execute -> validate
holistically -> record the cycle. Nothing is reported as a success unless the
plan ran and the validator passed it.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .absorption import absorb, propose_capabilities
from .capabilities import CapabilityError, CapabilityRegistry, bootstrap_native
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
    ) -> None:
        self.store = store
        self.registry = registry or CapabilityRegistry(store)
        bootstrap_native(self.registry)
        self.guardians = guardians or default_registry(store)
        self.pathfinder = pathfinder or PathFinder(store)
        self.validator = validator or HolisticValidator()
        self.synthesizer = Synthesizer(self.registry)

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
    ) -> EvolutionCycle:
        started = time.monotonic()

        consultation = self.guardians.consult(request, limit=limit, sources=sources)
        absorbed = absorb(self.store, consultation.units)
        proposals = propose_capabilities(consultation.units)

        plan = self.pathfinder.plan(initial, goal_type, operators_from(self.registry.list_active()))
        synthesis: SynthesisResult | None = None
        if not plan.solved and synthesize is not None:
            synthesis = self.synthesizer.synthesize(**synthesize)
            plan = self.pathfinder.plan(
                initial, goal_type, operators_from(self.registry.list_active())
            )

        execution: dict[str, Any] = {"ok": False, "reason": "no plan"}
        if plan.solved:
            execution = self._execute(plan, text if text is not None else request)

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
        )
        self.store.record_event(
            "cycle",
            {
                "request": request,
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
                    detail=f"{synthesis.reason}",
                    ref="verification driver",
                )
            )

        external_ok = len([s for s in consultation.ok_sources if s != "local"])
        constraints_addressed = len(_DECLARED_CONSTRAINTS)
        if synthesis is not None and not synthesis.admitted:
            constraints_addressed -= 1  # sandbox gate rejected the candidate

        context = {
            "sources_ok": len(consultation.ok_sources),
            "sources_total": len(consultation.sources),
            "external_sources_ok": external_ok,
            "units_total": len(consultation.units),
            "fresh_units": sum(1 for u in consultation.units if _is_fresh(u.provenance.retrieved_at)),
            "deterministic": True,
            "duration_s": duration,
            "budget_s": budget_s,
            "constraints_declared": len(_DECLARED_CONSTRAINTS),
            "constraints_addressed": max(0, constraints_addressed),
        }
        return self.validator.validate(request, claims, evidence, context)


def _is_fresh(timestamp: str, max_age_days: int = 730) -> bool:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).days <= max_age_days
