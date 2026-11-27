"""Functional capability fusion and a sovereignty audit.

The system can present one coherent capability map, a deterministic plan for a
goal that the current graph can reach, and one bounded improvement step. It
does not claim metaphysical unity, independence from its environment,
ontological perfection, or cosmic determinism. Those claims stay false and are
reported as false.
"""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any

from .contract import REQUIREMENTS
from .materialization import Materialization
from .metacurriculum import MetaCurriculum
from .pathfinder import operators_from

DOMAINS: tuple[dict[str, Any], ...] = (
    {
        "id": "mind",
        "label": "reasoning and retrieval",
        "modules": ["pathfinder", "ranking", "semantic", "context", "capabilities"],
    },
    {
        "id": "body",
        "label": "execution and materialization",
        "modules": ["execution", "orchestration", "materialization", "providers"],
    },
    {
        "id": "shield",
        "label": "openness and security",
        "modules": ["guard", "security", "protocol", "redteam"],
    },
    {
        "id": "immunity",
        "label": "validation and repair",
        "modules": ["validator", "gaps", "repair", "immunity"],
    },
    {
        "id": "determinism",
        "label": "deterministic planning",
        "modules": ["pathfinder", "orchestration", "quality"],
    },
    {
        "id": "excellence",
        "label": "quality and mastery",
        "modules": ["quality", "mastery", "metacurriculum"],
    },
    {
        "id": "essence",
        "label": "self-model and identity",
        "modules": ["selfhood", "selfmodel", "settings"],
    },
    {
        "id": "ascension",
        "label": "synthesis and acquisition",
        "modules": ["synthesis", "acquire", "blueprints", "absorption"],
    },
    {
        "id": "cosmic",
        "label": "bounded cosmic analogs",
        "modules": ["cosmic", "quantum", "hyper"],
    },
    {
        "id": "leadership",
        "label": "orchestration and contract",
        "modules": ["orchestration", "contract", "autonomy", "decisions"],
    },
)

_NON_CLAIMS = [
    "functional composition is not metaphysical unity",
    "deterministic search is not a guarantee that every goal is reachable",
    "bounded improvement is not ontological perfection",
    "no independence from hardware, energy, suppliers, capital, or law is claimed",
    "no cosmic determinism, retrocausality, or reality rewriting is claimed",
]


class CapabilityFusion:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.store = engine.store

    def fuse(self) -> dict[str, Any]:
        base = os.path.dirname(__file__)
        domains = []
        for domain in DOMAINS:
            present = [
                name for name in domain["modules"] if os.path.exists(os.path.join(base, f"{name}.py"))
            ]
            missing = [name for name in domain["modules"] if name not in present]
            domains.append(
                {
                    "id": domain["id"],
                    "label": domain["label"],
                    "modules": list(domain["modules"]),
                    "present": present,
                    "missing": missing,
                    "complete": not missing,
                }
            )
        links = []
        for left in domains:
            for right in domains:
                if left["id"] >= right["id"]:
                    continue
                shared = sorted(set(left["present"]) & set(right["present"]))
                if shared:
                    links.append(
                        {
                            "left": left["id"],
                            "right": right["id"],
                            "shared_modules": shared,
                        }
                    )
        capabilities = self.engine.registry.list_active()
        complete = sum(1 for domain in domains if domain["complete"])
        return {
            "domains": domains,
            "links": links,
            "capability_count": len(capabilities),
            "domain_count": len(domains),
            "complete_domains": complete,
            "cohesion": round(complete / len(domains), 4) if domains else 0.0,
            "single_entrypoints": [
                "/ask",
                "/evolve",
                "/orchestration/run",
                "/materialization/blueprint",
            ],
            "metaphysical_unity": False,
            "functional_composition": True,
            "note": (
                "One registry, one store, and shared modules connect the domains. "
                "This is a functional fabric, not a single metaphysical substance."
            ),
        }


class SovereigntyProtocol:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.store = engine.store
        self.fusion = CapabilityFusion(engine)
        self.materialization = Materialization(self.store)

    def plan(self, goal: str, initial: tuple[str, ...] = ("text",)) -> dict[str, Any]:
        text = str(goal).strip()
        if not text:
            raise ValueError("goal must not be empty")
        operators = operators_from(self.engine.registry.list_active())
        plan = self.engine.pathfinder.plan(initial, text, operators)
        steps = [step.capability for step in plan.steps]
        commitment = hashlib.sha256(
            f"{text}|{'|'.join(initial)}|{'|'.join(steps)}".encode("utf-8")
        ).hexdigest()[:16]
        return {
            "goal": text,
            "initial": list(initial),
            "solved": bool(plan.solved),
            "steps": steps,
            "explored": int(plan.explored),
            "reason": plan.reason,
            "deterministic_search": True,
            "guaranteed_success": False,
            "executed": False,
            "commitment": f"sovereignty.{commitment}",
            "failure_modes": [
                "a missing capability or type in the current graph",
                "a validation gate that rejects the produced evidence",
                "an external provider that is unreachable or unauthorized",
            ],
            "next_action": (
                "execute through /evolve or /orchestration/run and validate the result"
                if plan.solved
                else "synthesize or acquire the missing capability, then re-plan"
            ),
            "note": "a deterministic search over the current graph, not a cosmic guarantee",
        }

    def perfection(self, execute: bool = False, budget_s: float = 8.0) -> dict[str, Any]:
        budget = max(1.0, min(float(budget_s), 30.0))
        curriculum = MetaCurriculum(self.engine)
        table = curriculum.table(scenarios=50)
        choice = table[0] if table else {"goal": "markdown", "priority": 0.0}
        result: dict[str, Any] = {
            "executed": False,
            "choice": choice,
            "perfection_claim": False,
            "unbounded_loop": False,
            "budget_s": budget,
            "note": "one bounded improvement step; improvement is measured, not assumed",
        }
        if execute:
            run = curriculum.run(iterations=1, budget_s=budget, scenarios=50)
            result.update(
                {
                    "executed": True,
                    "run": run,
                    "measured_before": run["before"][:1],
                    "measured_after": run["after"][:1],
                }
            )
        return result

    def audit(self) -> dict[str, Any]:
        fused = self.fusion.fuse()
        closure = self.materialization.closure()
        checks = {
            "capability_fusion": {
                "functional": fused["cohesion"] == 1.0,
                "literal": False,
                "status": "functional composition across ten domains; not metaphysical unity",
            },
            "absolute_sovereignty": {
                "functional": False,
                "literal": False,
                "status": "depends on hardware, energy, suppliers, capital, and law",
            },
            "dynamic_perfection": {
                "functional": True,
                "literal": False,
                "status": "one bounded measured improvement step; no endless unbounded loop",
            },
            "cosmic_determinism": {
                "functional": False,
                "literal": False,
                "status": "deterministic graph search; reachability and validation can fail",
            },
            "ontological_perfection": {
                "functional": False,
                "literal": False,
                "status": "no perfect or final state is claimed",
            },
            "no_failure_no_delay": {
                "functional": False,
                "literal": False,
                "status": "failures and delays are recorded and drive reassignment",
            },
        }
        functional = sum(1 for check in checks.values() if check["functional"])
        literal = sum(1 for check in checks.values() if check["literal"])
        return {
            "checks": checks,
            "functional_met": functional,
            "literal_met": literal,
            "total": len(checks),
            "absolute_sovereignty": False,
            "cosmic_determinism": False,
            "ontological_perfection": False,
            "functional_fusion": fused["cohesion"] == 1.0,
            "contract": closure["summary"],
            "non_claims": list(_NON_CLAIMS),
            "verdict": "functional_fusion_available; absolute claims are false",
            "generated_at": time.time(),
        }

    def status(self) -> dict[str, Any]:
        fused = self.fusion.fuse()
        audit = self.audit()
        return {
            "fusion": fused,
            "audit": audit,
            "contract": {
                "total": len(REQUIREMENTS),
                "met": sum(1 for item in REQUIREMENTS if item["status"] == "met"),
                "partial": sum(1 for item in REQUIREMENTS if item["status"] == "partial"),
                "false": sum(1 for item in REQUIREMENTS if item["status"] == "false"),
            },
            "note": "the closest coherent whole; not a claim of absolute perfection",
        }
