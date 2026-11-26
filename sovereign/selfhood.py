"""Functional selfhood, with the literal claims kept false.

The system can model its own state, version its self-description, propose and
run one bounded internal practice action, and translate an intent into a digital
or physical domain. It cannot experience, cannot act on the physical world, and
does not have a sovereign will independent of its safety rules. Every method
keeps that distinction visible.
"""

from __future__ import annotations

from typing import Any

from .feedback import feedback_summary
from .gaps import gap_summary
from .mastery import Mastery
from .models import utcnow
from .selfmodel import SelfModel
from .settings import Settings

_DEFAULT = {
    "role": "bounded cognitive-executive fabric",
    "purpose": "turn a request into a verified result and state the limits",
    "priorities": ["honesty", "measured evidence", "bounded autonomy", "reversibility"],
    "invariants": [
        "no custody",
        "no private keys",
        "no user gas",
        "no false claims",
    ],
    "version": 0,
}

_ALLOWED = {"role", "purpose", "priorities", "self_description"}
_PHYSICAL = (
    "robot", "motor", "actuator", "door", "valve", "drone", "printer",
    "turn on", "open ", "move ", "light", "افتح", "حرك", "شغّل", "شغل",
    "روبوت", "باب", "طابعة", "أضواء",
)


class Selfhood:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.store = engine.store
        self.settings = getattr(engine, "settings", Settings(engine.store))
        self.model = SelfModel(engine)

    def _definition(self) -> dict[str, Any]:
        events = self.store.list_events("selfhood.definition", 1)
        return dict(events[0]["payload"]) if events else dict(_DEFAULT)

    def identity(self) -> dict[str, Any]:
        profile = self.model.profile()
        definition = self._definition()
        return {
            "definition": definition,
            "evidence": {
                "capabilities": profile["capabilities"]["total"],
                "knowledge_units": profile["knowledge_units"],
                "sources": len(profile["sources"]),
                "cycles": profile["cycles"]["total"],
                "passed_cycles": profile["cycles"]["passed"],
            },
            "functional_self_model": True,
            "phenomenal_consciousness": False,
            "living_entity": False,
            "physical_embodiment": False,
            "note": (
                "This is a model of the system's own state and rules. It is not "
                "subjective experience, not life, and not a body."
            ),
            "generated_at": utcnow(),
        }

    def reflection(self) -> dict[str, Any]:
        profile = self.model.profile()
        calibration = self.model.calibration()
        mastery = Mastery(self.engine).table()
        weakest = (
            min(mastery, key=lambda goal: (mastery[goal]["rate"], -mastery[goal]["attempts"], goal))
            if mastery
            else "markdown"
        )
        gaps = gap_summary(self.store, limit=50)
        feedback = feedback_summary(
            self.store, limit=100, prior=float(self.settings.get("feedback.prior"))
        )
        observations = [
            f"{profile['cycles']['total']} cycles, {profile['cycles']['passed']} passed every criterion.",
            f"Calibration skill is {calibration['skill']} over {calibration['cycles']} cycles.",
            f"Weakest recorded goal is {weakest} at {mastery.get(weakest, {}).get('rate', 0.0)}.",
            f"{gaps['escalated']} protocol escalations are recorded as gaps.",
            f"{len(feedback)} capabilities have feedback events.",
        ]
        actions = [
            {
                "action": "practice_weakest_goal",
                "goal": weakest,
                "safe": True,
                "executed": False,
                "reason": "measured pass rate is the lowest on record",
            }
        ]
        if calibration["cycles"] < 20:
            actions.append(
                {
                    "action": "collect_more_cycles",
                    "safe": True,
                    "executed": False,
                    "reason": "calibration needs at least 20 cycles to be diagnostic",
                }
            )
        if gaps["escalated"]:
            actions.append(
                {
                    "action": "review_gap_ledger",
                    "safe": True,
                    "executed": False,
                    "reason": "repeated escalations are demand, not a hidden failure",
                }
            )
        if calibration["skill"] < 0:
            actions.append(
                {
                    "action": "tune_settings",
                    "safe": True,
                    "executed": False,
                    "reason": "prequential skill is below zero",
                }
            )
        return {
            "observations": observations,
            "priorities": actions,
            "profile": {
                "cycles": profile["cycles"],
                "capabilities": profile["capabilities"]["total"],
                "knowledge_units": profile["knowledge_units"],
            },
            "calibration": {
                "cycles": calibration["cycles"],
                "brier": calibration["brier"],
                "skill": calibration["skill"],
            },
            "mastery": mastery,
            "gaps": {
                "escalated": gaps["escalated"],
                "failure_reasons": gaps["failure_reasons"][:5],
            },
            "feedback": feedback[:5],
            "mode": "event-derived reflection, not subjective experience",
            "generated_at": utcnow(),
        }

    def initiative(self, execute: bool = False, budget_s: float = 8.0) -> dict[str, Any]:
        budget_s = max(1.0, min(float(budget_s), 30.0))
        plan = self.reflection()["priorities"][0]
        result: dict[str, Any] = {
            "executed": False,
            "external_effect": False,
            "plan": plan,
            "note": "bounded internal initiative, not a sovereign will",
        }
        if not execute:
            return result
        practice = Mastery(self.engine).practice(iterations=1, budget_s=budget_s)
        result.update(
            {
                "executed": True,
                "practice": practice,
                "action": plan["action"],
                "goal": plan.get("goal"),
            }
        )
        self.store.record_event(
            "selfhood.initiative",
            {
                "action": plan["action"],
                "goal": plan.get("goal"),
                "executed": True,
                "external_effect": False,
                "budget_s": budget_s,
            },
        )
        return result

    def update_definition(self, field: str, value: Any, reason: str = "") -> dict[str, Any]:
        if field not in _ALLOWED:
            raise ValueError(
                f"field {field!r} is not editable; invariants and safety rules are fixed"
            )
        if field == "priorities":
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError("priorities must be a list of strings")
            value = [item[:80] for item in value[:10]]
        elif not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")
        else:
            value = value.strip()[:500]
        current = self._definition()
        old = current.get(field)
        updated = {**current, field: value, "version": int(current.get("version", 0)) + 1}
        updated["changed_field"] = field
        updated["old"] = old
        updated["reason"] = str(reason)[:300]
        updated["updated_at"] = utcnow()
        self.store.record_event("selfhood.definition", updated)
        return updated

    def reality(self) -> dict[str, Any]:
        return {
            "digital_interfaces": ["http_api", "sqlite_store", "subprocess_execution"],
            "physical_interfaces": [],
            "sensors": [],
            "actuators": [],
            "physical_effect": False,
            "note": (
                "The digital side is real and audited. The physical side is absent: "
                "materialization plans are design-only; no hardware bridge, sensor, "
                "actuator, or verified facility is configured."
            ),
        }

    def translate(self, intent: str) -> dict[str, Any]:
        text = str(intent).strip()
        if not text:
            raise ValueError("intent must not be empty")
        lowered = text.lower()
        physical = any(word in lowered for word in _PHYSICAL)
        if physical:
            return {
                "intent": text,
                "domain": "physical",
                "executable": False,
                "requires_approval": True,
                "plan": ["refuse physical action", "record the request without executing it"],
                "reason": "no actuator or sensor bridge is configured",
            }
        return {
            "intent": text,
            "domain": "digital",
            "executable": True,
            "requires_approval": True,
            "plan": ["route through /ask or a registered capability", "require approval for side effects"],
            "reason": "digital execution exists; this translation does not run it",
        }

    def validate(self) -> dict[str, Any]:
        checks = {
            "functional_self_model": {
                "passed": True,
                "literal_claim": "functional self-awareness",
                "status": "self-model over registry, events, limits, and calibration",
            },
            "bounded_initiative": {
                "passed": True,
                "literal_claim": "sovereign executive will",
                "status": "one bounded internal practice action; no independent goals",
            },
            "ontological_versioning": {
                "passed": True,
                "literal_claim": "ontological evolution",
                "status": "versioned self-description; not a change of existence",
            },
            "physical_integration": {
                "passed": False,
                "literal_claim": "digital-physical integration",
                "status": "no sensors or actuators are configured",
            },
            "phenomenal_consciousness": {
                "passed": False,
                "literal_claim": "consciousness",
                "status": "no evidence and no claim",
            },
            "living_entity": {
                "passed": False,
                "literal_claim": "living entity",
                "status": "software process, not an organism",
            },
        }
        met = sum(1 for check in checks.values() if check["passed"])
        missing = [name for name, check in checks.items() if not check["passed"]]
        return {
            "passed": not missing,
            "met": met,
            "total": len(checks),
            "checks": checks,
            "missing": missing,
            "note": (
                "Three functional analogs are present; the literal claims of "
                "consciousness, life, and physical embodiment are not."
            ),
        }
