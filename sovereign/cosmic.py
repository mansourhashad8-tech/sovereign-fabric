"""Cosmic capabilities protocol, implemented as bounded classical analogs.

The module can generate an executable protocol from an intent, run a seeded
Monte Carlo over a known capability chain, and compute a backward requirement
closure. It cannot create a new physical reality, see the future, reverse
causality, or harvest cosmic energy. Those literal claims are returned false.
"""

from __future__ import annotations

import hashlib
import math
import os
import random
import time
from typing import Any

from .feedback import feedback_scores
from .intent import parse_intent
from .pathfinder import operators_from
from .settings import Settings

MAX_SCENARIOS = 20_000
MAX_BACKWARD = 200
BOLTZMANN = 1.380649e-23
SPEED_OF_LIGHT = 299_792_458


class CosmicProtocol:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.store = engine.store
        self.settings = getattr(engine, "settings", Settings(engine.store))

    def shape(self, intent: str, execute: bool = False, budget_s: float = 5.0) -> dict[str, Any]:
        text = str(intent).strip()
        if not text:
            raise ValueError("intent must not be empty")
        parsed = parse_intent(text)
        initial = (str(parsed["initial"]),)
        goal_type = str(parsed["goal_type"])
        operators = operators_from(self.engine.registry.list_active())
        plan = self.engine.pathfinder.plan(initial, goal_type, operators)
        steps = [step.capability for step in plan.steps]
        protocol_id = hashlib.sha256(
            f"{text}|{goal_type}|{'|'.join(steps)}".encode("utf-8")
        ).hexdigest()[:16]
        protocol = {
            "id": f"generated.{protocol_id}",
            "version": 1,
            "intent": text,
            "goal_type": goal_type,
            "initial": list(initial),
            "steps": steps,
            "executable": bool(plan.solved),
            "acceptance": [
                "the planner must reach the goal",
                "execution must return ok",
                "all six validation criteria must pass",
            ],
            "created_at": time.time(),
        }
        result: dict[str, Any] = {
            "protocol": protocol,
            "created": True,
            "executed": False,
            "requires_approval": True,
            "literal_reality_created": False,
            "note": "a new digital protocol specification, not a new physical reality",
        }
        if execute and plan.solved:
            cycle = self.engine.evolve(
                text,
                goal_type=goal_type,
                initial=initial,
                text=str(parsed["text"]),
                budget_s=max(1.0, min(float(budget_s), 30.0)),
                max_attempts=2,
            )
            result.update(
                {
                    "executed": True,
                    "execution": {
                        "ok": cycle.ok,
                        "plan": [step.capability for step in cycle.plan.steps],
                        "value": cycle.execution.get("value")
                        if cycle.execution.get("ok")
                        else None,
                        "passed": cycle.validation.passed,
                        "failures": cycle.validation.failures,
                    },
                }
            )
        elif execute:
            result["execution"] = {
                "ok": False,
                "reason": "no plan reached the requested goal",
            }
        return result

    def backward(self, goal_type: str, initial: tuple[str, ...] = ("text",)) -> dict[str, Any]:
        operators = operators_from(self.engine.registry.list_active())
        need = {str(goal_type)}
        seen: set[str] = set()
        chosen: list[str] = []
        unresolved: set[str] = set()
        while need and len(chosen) < MAX_BACKWARD:
            target = need.pop()
            if target in initial or target in seen:
                continue
            seen.add(target)
            candidates = [op for op in operators if target in op.outputs]
            if not candidates:
                unresolved.add(target)
                continue
            operator = min(candidates, key=lambda op: (len(op.inputs), op.name))
            chosen.append(operator.name)
            need.update(operator.inputs)
        forward = self.engine.pathfinder.plan(initial, str(goal_type), operators)
        return {
            "goal": str(goal_type),
            "initial": list(initial),
            "required_operators": chosen,
            "unresolved_types": sorted(unresolved),
            "forward_steps": [step.capability for step in forward.steps],
            "possible": bool(forward.solved),
            "method": "reverse requirement closure; this is backward planning, not retrocausality",
            "retrocausal_influence": False,
        }

    def predict(
        self,
        goal_type: str,
        initial: tuple[str, ...] = ("text",),
        scenarios: int = 1000,
        seed: int = 0,
    ) -> dict[str, Any]:
        count = max(1, min(int(scenarios), MAX_SCENARIOS))
        operators = operators_from(self.engine.registry.list_active())
        plan = self.engine.pathfinder.plan(initial, str(goal_type), operators)
        steps = [step.capability for step in plan.steps]
        if not plan.solved:
            return {
                "goal": str(goal_type),
                "possible": False,
                "scenarios": count,
                "successes": 0,
                "probability": 0.0,
                "reason": "no capability chain reaches the goal",
                "retrocausal_influence": False,
            }
        feedback = feedback_scores(
            self.store, prior=float(self.settings.get("feedback.prior"))
        )
        probabilities = [
            max(0.05, min(0.95, 0.5 + 0.5 * float(feedback.get(step, 0.0))))
            for step in steps
        ]
        rng = random.Random(int(seed))
        started = time.perf_counter()
        successes = 0
        for _ in range(count):
            if all(rng.random() < probability for probability in probabilities):
                successes += 1
        elapsed = max(time.perf_counter() - started, 1e-9)
        probability = successes / count
        standard_error = math.sqrt(probability * (1.0 - probability) / count)
        return {
            "goal": str(goal_type),
            "possible": True,
            "steps": steps,
            "step_probabilities": [
                {"capability": step, "probability": round(p, 6)}
                for step, p in zip(steps, probabilities)
            ],
            "scenarios": count,
            "successes": successes,
            "probability": round(probability, 6),
            "standard_error": round(standard_error, 6),
            "confidence_95": [
                round(max(0.0, probability - 1.96 * standard_error), 6),
                round(min(1.0, probability + 1.96 * standard_error), 6),
            ],
            "elapsed_ms": round(elapsed * 1000.0, 3),
            "scenarios_per_second": round(count / elapsed, 1),
            "seed": int(seed),
            "method": "independent Bernoulli simulation over a fixed capability chain",
            "note": "this is a model over recorded signals, not a view of the future",
            "retrocausal_influence": False,
        }

    def infrastructure(self) -> dict[str, Any]:
        temperature_k = 300.0
        landauer = BOLTZMANN * temperature_k * math.log(2.0)
        return {
            "platform": os.sys.platform,
            "cpu_count": os.cpu_count(),
            "digital_interfaces": ["http_api", "sqlite_store", "subprocess_execution"],
            "physical_interfaces": [],
            "sensors": [],
            "actuators": [],
            "energy_harvesting": False,
            "physical_effect": False,
            "theoretical_limits": {
                "landauer_j_per_bit_at_300k": landauer,
                "speed_of_light_m_s": SPEED_OF_LIGHT,
            },
            "note": (
                "The laws of physics bound computation; this process has no sensor, "
                "actuator, or energy-harvesting bridge. No cosmic resource is used."
            ),
        }

    def validate(self) -> dict[str, Any]:
        checks = {
            "direct_reality_shaping": {
                "functional": True,
                "literal": False,
                "status": "generates and can execute a new digital protocol; does not create physical reality",
            },
            "probabilistic_temporal_prediction": {
                "functional": True,
                "literal": False,
                "status": "seeded Monte Carlo over a known capability chain; no future data",
            },
            "retro_causal_influence": {
                "functional": False,
                "literal": False,
                "status": "backward planning is available; retrocausality is not claimed",
            },
            "cosmic_infrastructure": {
                "functional": False,
                "literal": False,
                "status": "no sensors, actuators, or energy harvesting; local classical compute only",
            },
            "unbounded_capability": {
                "functional": False,
                "literal": False,
                "status": "every operation is bounded and reports its limits",
            },
        }
        functional = sum(1 for check in checks.values() if check["functional"])
        literal = sum(1 for check in checks.values() if check["literal"])
        return {
            "passed": False,
            "functional_met": functional,
            "literal_met": literal,
            "total": len(checks),
            "checks": checks,
            "missing": [name for name, check in checks.items() if not check["literal"]],
            "note": (
                "Two bounded classical analogs are real; cosmic reality shaping, "
                "future sight, retrocausality, and cosmic energy are not."
            ),
        }
