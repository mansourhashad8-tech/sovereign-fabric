"""One request, one trace, one honest verdict.

The transformation path composes the existing layers: intent parsing, graph
planning, local execution, optional remote dispatch, materialization planning,
validation, and the demand ledger. It does not claim a literal transformation
of the system into a physical or absolute entity.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from .demands import DemandLedger
from .intent import parse_intent
from .materialization import Materialization
from .orchestration import Orchestrator, Task
from .sovereignty import SovereigntyProtocol

_PHYSICAL = (
    "robot", "printer", "sensor", "battery", "solar", "build a", "manufactur",
    "روبوت", "طابعة", "حساس", "بطارية", "طاقة", "ابن", "صنع", "تصنيع",
)


class TransformationEngine:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.store = engine.store
        self.sovereignty = SovereigntyProtocol(engine)
        self.materialization = Materialization(self.store)
        self.demands = DemandLedger(self.store)

    def _is_physical(self, text: str) -> bool:
        lowered = text.casefold()
        return any(token in lowered for token in _PHYSICAL)

    def _digital(self, text: str, parsed: dict[str, Any], budget_s: float) -> dict[str, Any]:
        initial = parsed["initial"]
        initial = (str(initial),) if isinstance(initial, str) else tuple(initial)
        plan = self.sovereignty.plan(str(parsed["goal_type"]), initial)
        if not plan["solved"]:
            return {
                "executed": False,
                "plan": plan,
                "status": "blocked",
                "validation": {"passed": False, "failures": ["no plan reached the goal"]},
                "next_action": plan["next_action"],
            }
        cycle = self.engine.evolve(
            text,
            goal_type=str(parsed["goal_type"]),
            initial=initial,
            text=str(parsed["text"]),
            budget_s=budget_s,
            max_attempts=2,
            local_transform=True,
        )
        passed = bool(cycle.validation.passed)
        executed = bool(cycle.execution.get("ok"))
        status = "completed" if cycle.ok and passed else ("partial" if executed else "failed")
        return {
            "executed": executed,
            "plan": plan,
            "status": status,
            "execution": {
                "ok": executed,
                "value": cycle.execution.get("value") if executed else None,
                "plan": [step.capability for step in cycle.plan.steps],
            },
            "validation": {
                "passed": passed,
                "failures": list(cycle.validation.failures),
            },
            "next_action": (
                "the measured result is valid; keep the trace"
                if status == "completed"
                else "inspect the validation failures and re-plan or acquire the missing capability"
            ),
        }

    def _material(self, text: str, quantity: int, budget_usd: float) -> dict[str, Any]:
        plan = self.materialization.blueprint(text, quantity=quantity, budget_usd=budget_usd)
        economy = self.materialization.economy(
            text, quantity=quantity, budget_usd=budget_usd
        )
        return {
            "executed": False,
            "plan": plan,
            "economy": economy,
            "status": "design_only",
            "validation": {
                "passed": False,
                "failures": ["no physical build was measured"],
            },
            "next_action": "verify a fabrication cell, feedstock, energy, and funding before a build",
        }

    def _remote(self, text: str, execute_remote: bool) -> dict[str, Any]:
        if not execute_remote:
            return {
                "executed": False,
                "status": "blocked",
                "validation": {"passed": False, "failures": ["remote execution not authorized"]},
                "next_action": "set execute_remote=true to dispatch the bounded workflow",
            }
        orchestrator = Orchestrator(self.store)
        task = Task(
            id="transform-remote",
            capability="compute.python",
            payload={"task": "tests", "ref": "main"},
            standard="reproducibility",
        )
        run = orchestrator.run([task], max_replacements=0)
        item = run["results"][0] if run.get("results") else {}
        return {
            "executed": bool(item.get("run_id")),
            "status": run["status"],
            "remote": item,
            "validation": item.get("quality", {"passed": False, "failures": ["no remote result"]}),
            "next_action": (
                "keep the observed run"
                if item.get("quality", {}).get("passed")
                else "inspect the remote failure and reassign or retry"
            ),
        }

    def execute(
        self,
        intent: str,
        mode: str = "auto",
        budget_s: float = 8.0,
        quantity: int = 1,
        budget_usd: float = 0.0,
        execute_remote: bool = False,
    ) -> dict[str, Any]:
        text = str(intent).strip()
        if not text:
            raise ValueError("intent must not be empty")
        budget = max(1.0, min(float(budget_s), 30.0))
        quantity = max(1, min(int(quantity), 1000))
        budget_usd = max(0.0, float(budget_usd))
        parsed = parse_intent(text)
        selected = mode
        if selected == "auto":
            selected = "material" if self._is_physical(text) else "digital"
        if selected not in {"digital", "material", "remote"}:
            raise ValueError("mode must be auto, digital, material, or remote")

        started = time.perf_counter()
        if selected == "material":
            outcome = self._material(text, quantity, budget_usd)
        elif selected == "remote":
            outcome = self._remote(text, execute_remote)
        else:
            outcome = self._digital(text, parsed, budget)
        duration = time.perf_counter() - started
        trace = {
            "id": f"transform.{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}",
            "intent_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
            "mode": selected,
            "goal_type": parsed["goal_type"],
            "initial": [parsed["initial"]] if isinstance(parsed["initial"], str) else list(parsed["initial"]),
            "status": outcome["status"],
            "executed": outcome["executed"],
            "validated": bool(outcome["validation"].get("passed")),
            "validation": outcome["validation"],
            "plan": outcome.get("plan"),
            "economy": outcome.get("economy"),
            "remote": outcome.get("remote"),
            "duration_s": round(duration, 4),
            "physical_built": False,
            "physical_effect": False,
            "literal_transformation": False,
            "guaranteed_success": False,
            "next_action": outcome["next_action"],
            "note": (
                "One composed trace. It does not claim a body, absolute sovereignty, "
                "cosmic determinism, or guaranteed success."
            ),
            "created_at": time.time(),
        }
        self.store.record_event(
            "transformation.run",
            {
                "id": trace["id"],
                "intent_hash": trace["intent_hash"],
                "mode": selected,
                "status": trace["status"],
                "executed": trace["executed"],
                "validated": trace["validated"],
                "duration_s": trace["duration_s"],
            },
        )
        return trace

    def self_transform(self, execute: bool = False, budget_s: float = 8.0) -> dict[str, Any]:
        budget = max(1.0, min(float(budget_s), 30.0))
        from .metacurriculum import MetaCurriculum

        curriculum = MetaCurriculum(self.engine)
        before = curriculum.table(scenarios=20)
        choice = before[0] if before else {"goal": "markdown"}
        result: dict[str, Any] = {
            "executed": False,
            "choice": choice,
            "before": before[:3],
            "after": [],
            "literal_transformation": False,
            "perfection_claim": False,
            "unbounded_loop": False,
            "budget_s": budget,
            "note": "one bounded measured improvement step; improvement is not assumed",
        }
        if execute:
            run = curriculum.run(iterations=1, budget_s=budget, scenarios=20)
            result.update(
                {
                    "executed": True,
                    "after": run["after"][:3],
                    "run": run,
                }
            )
        self.store.record_event(
            "transformation.self",
            {
                "executed": result["executed"],
                "choice": result["choice"].get("goal"),
                "literal_transformation": False,
                "budget_s": budget,
            },
        )
        return result

    def status(self) -> dict[str, Any]:
        demand = self.demands.report()["summary"]
        audit = self.sovereignty.audit()
        readiness = self.materialization.readiness()
        return {
            "mode": "unified_execution",
            "operational_transformation": True,
            "literal_transformation": False,
            "physical_body": False,
            "physical_sovereignty": readiness["physical_sovereignty"],
            "demand_summary": demand,
            "sovereignty": {
                "functional_fusion": audit["functional_fusion"],
                "absolute_sovereignty": audit["absolute_sovereignty"],
                "cosmic_determinism": audit["cosmic_determinism"],
                "ontological_perfection": audit["ontological_perfection"],
            },
            "last_runs": self.store.list_events("transformation.run", 5),
            "note": "one executable path across the layers; not a literal ontological transformation",
        }
