"""Materialization planning with explicit physical limits.

This module designs a manufacturable article, estimates its bill of materials,
assembly, energy, cost, and lead time, and builds a digital twin. It does not
claim that anything was printed, assembled, purchased, energized, or installed.
No printer, robot, feedstock, facility, actuator, or capital account is present
unless the corresponding interface is configured and verified.
"""

from __future__ import annotations

import hashlib
import math
import os
import time
from typing import Any

ARCHETYPES: dict[str, dict[str, Any]] = {
    "robot": {
        "name": "mobile robot cell",
        "keywords": ("robot", "robotic", "arm", "drone", " rover", "روبوت", "ذراع", "طائرة"),
        "components": [
            ("structural frame", "aluminium extrusion kit", 1, 3.2, 180.0, 7),
            ("controller", "industrial ARM SBC", 1, 0.4, 220.0, 10),
            ("actuators", "servo motor pair", 2, 1.1, 160.0, 14),
            ("sensors", "camera and IMU module", 1, 0.2, 140.0, 7),
            ("power", "24 V battery pack", 1, 1.8, 190.0, 10),
            ("fasteners", "metric fastener set", 1, 0.3, 25.0, 3),
        ],
        "tools": ["3D printer", "CNC or drill press", "assembly jig", "multimeter"],
        "hazards": ["pinch points", "electrical shock", "battery thermal risk"],
        "standards": ["ISO 12100", "IEC 60204-1"],
        "quality_gates": ["continuity", "emergency stop", "payload test", "thermal soak"],
        "assembly_hours": 12.0,
        "energy_kwh": 4.5,
    },
    "sensor": {
        "name": "environmental sensor node",
        "keywords": ("sensor", "monitor", "weather", "حساس", "مستشعر", "مراقبة"),
        "components": [
            ("enclosure", "IP65 printed enclosure", 1, 0.3, 18.0, 2),
            ("controller", "low-power MCU board", 1, 0.1, 22.0, 5),
            ("sensing", "temperature/humidity/pressure module", 1, 0.1, 35.0, 5),
            ("power", "solar cell and battery", 1, 0.5, 45.0, 7),
            ("fasteners", "stainless fastener set", 1, 0.1, 8.0, 3),
        ],
        "tools": ["3D printer", "soldering iron", "multimeter"],
        "hazards": ["soldering burns", "battery thermal risk", "weather exposure"],
        "standards": ["IEC 60529", "IEC 61010-1"],
        "quality_gates": ["seal test", "sensor calibration", "power budget", "logger test"],
        "assembly_hours": 3.0,
        "energy_kwh": 0.6,
    },
    "printer": {
        "name": "desktop fabrication cell",
        "keywords": ("printer", "3d print", "fabricat", "طابعة", "طباعة", "تصنيع"),
        "components": [
            ("frame", "steel and extrusion frame", 1, 6.0, 260.0, 10),
            ("motion", "linear rail and stepper kit", 1, 2.5, 240.0, 14),
            ("hotend", "heated nozzle assembly", 1, 0.4, 90.0, 7),
            ("controller", "motion controller board", 1, 0.3, 110.0, 7),
            ("power", "24 V enclosed supply", 1, 1.2, 80.0, 7),
        ],
        "tools": ["frame jig", "multimeter", "caliper", "screwdriver set"],
        "hazards": ["hot surface", "electrical shock", "moving axes"],
        "standards": ["IEC 60204-1", "ISO 12100"],
        "quality_gates": ["squareness", "axis travel", "temperature accuracy", "first article"],
        "assembly_hours": 10.0,
        "energy_kwh": 3.2,
    },
    "energy": {
        "name": "standalone energy node",
        "keywords": ("energy", "solar", "battery", "power", "طاقة", "كهرباء", "بطارية"),
        "components": [
            ("generation", "solar panel", 2, 12.0, 180.0, 10),
            ("storage", "LiFePO4 battery", 1, 12.0, 420.0, 14),
            ("conversion", "MPPT charge controller", 1, 1.0, 120.0, 7),
            ("protection", "breaker and enclosure", 1, 2.0, 90.0, 5),
            ("mounting", "rail and cable kit", 1, 2.0, 55.0, 5),
        ],
        "tools": ["crimper", "multimeter", "torque wrench", "insulation tester"],
        "hazards": ["DC arc", "battery thermal risk", "fall hazard during mounting"],
        "standards": ["IEC 62109", "IEC 62619"],
        "quality_gates": ["insulation resistance", "ground continuity", "charge/discharge", "thermal check"],
        "assembly_hours": 8.0,
        "energy_kwh": 0.8,
    },
    "compute": {
        "name": "edge compute node",
        "keywords": ("computer", "server", "compute", "gpu", "حاسوب", "خادم", "حوسبة"),
        "components": [
            ("compute", "edge SBC with accelerator", 1, 0.6, 320.0, 10),
            ("storage", "NVMe SSD", 1, 0.1, 80.0, 5),
            ("enclosure", "fanless metal enclosure", 1, 1.2, 60.0, 5),
            ("power", "DC supply and UPS", 1, 2.0, 130.0, 7),
            ("network", "ethernet and antenna kit", 1, 0.3, 45.0, 5),
        ],
        "tools": ["anti-static mat", "screwdriver set", "multimeter"],
        "hazards": ["electrical shock", "thermal throttling", "data loss"],
        "standards": ["IEC 62368-1", "IEC 61000"],
        "quality_gates": ["boot test", "storage integrity", "thermal soak", "network test"],
        "assembly_hours": 4.0,
        "energy_kwh": 1.5,
    },
    "generic": {
        "name": "general fabrication article",
        "keywords": (),
        "components": [
            ("structure", "aluminium extrusion", 2, 2.0, 70.0, 5),
            ("fasteners", "metric fastener set", 1, 0.3, 20.0, 3),
            ("controller", "programmable controller", 1, 0.3, 90.0, 7),
            ("wiring", "wire and connector kit", 1, 0.4, 35.0, 4),
        ],
        "tools": ["drill press", "screwdriver set", "multimeter"],
        "hazards": ["sharp edges", "electrical shock"],
        "standards": ["ISO 12100"],
        "quality_gates": ["dimensional check", "continuity", "functional test"],
        "assembly_hours": 5.0,
        "energy_kwh": 1.2,
    },
}

_READINESS_ENV = {
    "printer": "SOVEREIGN_PRINTER_ENDPOINT",
    "robot": "SOVEREIGN_ROBOT_ENDPOINT",
    "feedstock": "SOVEREIGN_FEEDSTOCK_KG",
    "facility": "SOVEREIGN_FACILITY",
    "energy": "SOVEREIGN_ENERGY_KW",
    "capital": "SOVEREIGN_CAPITAL_USD",
}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _archetype(intent: str) -> dict[str, Any]:
    lowered = intent.casefold()
    for name, archetype in ARCHETYPES.items():
        if name == "generic":
            continue
        if any(keyword.casefold() in lowered for keyword in archetype["keywords"]):
            return archetype
    return ARCHETYPES["generic"]


class Materialization:
    def __init__(self, store=None) -> None:
        self.store = store

    def readiness(self) -> dict[str, Any]:
        interfaces: dict[str, dict[str, Any]] = {}
        for name, env_key in _READINESS_ENV.items():
            raw = os.environ.get(env_key, "").strip()
            configured = bool(raw)
            interfaces[name] = {
                "env": env_key,
                "configured": configured,
                "verified": False,
                "kind": "external_interface" if name not in {"capital", "feedstock"} else "resource",
            }
        capital = _number(os.environ.get("SOVEREIGN_CAPITAL_USD", "0"))
        feedstock_kg = _number(os.environ.get("SOVEREIGN_FEEDSTOCK_KG", "0"))
        energy_kw = _number(os.environ.get("SOVEREIGN_ENERGY_KW", "0"))
        blocked = [
            name
            for name, item in interfaces.items()
            if not item["configured"]
        ]
        return {
            "interfaces": interfaces,
            "capital_usd": capital,
            "feedstock_kg": feedstock_kg,
            "energy_kw": energy_kw,
            "physical_sovereignty": False,
            "self_manufacturing_ready": False,
            "design_ready": True,
            "blocked_by": blocked,
            "verified_physical_effect": False,
            "note": (
                "Configured interfaces are not verified hardware. No physical build, "
                "actuation, energy harvest, or autonomous purchase is claimed."
            ),
        }

    def blueprint(
        self,
        intent: str,
        quantity: int = 1,
        site: str = "unspecified",
        budget_usd: float = 0.0,
    ) -> dict[str, Any]:
        text = str(intent).strip()
        if not text:
            raise ValueError("intent must not be empty")
        quantity = max(1, min(int(quantity), 1000))
        budget_usd = max(0.0, float(budget_usd))
        archetype = _archetype(text)
        bom = []
        total_mass = 0.0
        total_cost = 0.0
        lead_days = 0
        for part, spec, qty, mass_kg, cost_usd, lead in archetype["components"]:
            scaled_qty = int(qty) * quantity
            line_mass = float(mass_kg) * scaled_qty
            line_cost = float(cost_usd) * scaled_qty
            total_mass += line_mass
            total_cost += line_cost
            lead_days = max(lead_days, int(lead))
            bom.append(
                {
                    "part": part,
                    "spec": spec,
                    "quantity": scaled_qty,
                    "mass_kg": round(line_mass, 3),
                    "cost_usd": round(line_cost, 2),
                    "lead_days": int(lead),
                    "supplier_type": "industrial distributor or local fabricator",
                }
            )
        assembly_hours = float(archetype["assembly_hours"]) * quantity
        energy_kwh = float(archetype["energy_kwh"]) * quantity
        shortfall = round(max(0.0, total_cost - budget_usd), 2)
        reliability = max(0.5, 0.98 - 0.01 * len(bom))
        readiness = self.readiness()
        digest = hashlib.sha256(
            f"{text}|{quantity}|{site}|{archetype['name']}".encode("utf-8")
        ).hexdigest()[:16]
        return {
            "id": f"materialization.{digest}",
            "intent": text,
            "archetype": archetype["name"],
            "quantity": quantity,
            "site": str(site)[:200],
            "bom": bom,
            "totals": {
                "mass_kg": round(total_mass, 3),
                "cost_usd": round(total_cost, 2),
                "assembly_hours": round(assembly_hours, 2),
                "energy_kwh": round(energy_kwh, 3),
                "lead_days": lead_days,
            },
            "budget": {
                "budget_usd": round(budget_usd, 2),
                "shortfall_usd": shortfall,
                "status": "unfunded" if budget_usd <= 0 else ("within_budget" if shortfall == 0 else "shortfall"),
            },
            "tools_required": list(archetype["tools"]),
            "assembly_steps": [
                "verify the bill of materials and traceable part numbers",
                "prepare the facility, tools, and safety controls",
                "fabricate or print structural parts to the drawing",
                "assemble the mechanical and electrical subassemblies",
                "flash and test the controller with the digital twin",
                "run the declared quality gates and record measurements",
            ],
            "hazards": list(archetype["hazards"]),
            "standards": list(archetype["standards"]),
            "quality_gates": list(archetype["quality_gates"]),
            "digital_twin": {
                "model": "mass, energy, cost, and lead-time arithmetic",
                "estimated_reliability": round(reliability, 3),
                "measured": False,
                "physical_built": False,
                "note": "an engineering estimate, not a test result",
            },
            "readiness": readiness,
            "physical_built": False,
            "physical_effect": False,
            "requires_facility": True,
            "requires_human_oversight": True,
            "self_manufacturing_ready": False,
            "materialization_status": "design_and_digital_twin_only",
            "blocked_by": readiness["blocked_by"],
            "next_actions": [
                "provide a verified fabrication facility and machine endpoints",
                "provide feedstock, energy, and a funded capital account",
                "complete a safety review before energizing or moving anything",
                "run the first article inspection and record measurements",
            ],
            "created_at": time.time(),
            "note": (
                "A buildable plan and digital twin are produced. No part was "
                "purchased, printed, assembled, energized, or installed."
            ),
        }

    def economy(
        self,
        intent: str,
        quantity: int = 1,
        budget_usd: float = 0.0,
        unit_price_usd: float | None = None,
    ) -> dict[str, Any]:
        plan = self.blueprint(intent, quantity=quantity, budget_usd=budget_usd)
        units = max(1, int(plan["quantity"]))
        unit_cost = plan["totals"]["cost_usd"] / units
        price = _number(unit_price_usd, round(unit_cost * 1.4, 2)) if unit_price_usd is not None else round(unit_cost * 1.4, 2)
        margin = price - unit_cost
        fixed_cost = round(plan["totals"]["cost_usd"] * 0.2, 2)
        break_even = math.ceil(fixed_cost / margin) if margin > 0 else None
        capital_required = round(plan["totals"]["cost_usd"] + fixed_cost, 2)
        return {
            "blueprint_id": plan["id"],
            "unit_cost_usd": round(unit_cost, 2),
            "unit_price_usd": round(price, 2),
            "unit_margin_usd": round(margin, 2),
            "fixed_cost_usd": fixed_cost,
            "break_even_units": break_even,
            "capital_required_usd": capital_required,
            "capital_available_usd": plan["budget"]["budget_usd"],
            "capital_gap_usd": round(max(0.0, capital_required - plan["budget"]["budget_usd"]), 2),
            "sovereign": False,
            "revenue_claim": False,
            "external_dependencies": plan["blocked_by"],
            "assumptions": [
                "cost is an engineering estimate, not a supplier quote",
                "demand, tax, warranty, and maintenance are not modeled",
                "no customer, contract, or payment channel is present",
            ],
            "note": (
                "Unit economics and a break-even estimate are provided. No revenue, "
                "capital, customer, or self-sustaining economy is claimed."
            ),
        }

    def closure(self) -> dict[str, Any]:
        from .contract import REQUIREMENTS

        nearest = {
            "multimodal_quantum": "Hugging Face metadata is available; no multimodal model or quantum backend is configured",
            "self_generating_code": "bounded synthesis and acquisition, not arbitrary self-rewrite",
            "hyper_kernel": "classical HRR memory and in-process bus",
            "sovereign_will": "one bounded initiative action under fixed safety invariants",
            "ontological_evolution": "versioned self-description; invariants stay fixed",
            "digital_physical": "materialization blueprint and digital twin; no actuator or physical effect",
            "cosmic_protocol": "protocol generation and Monte Carlo planning; no literal reality shaping",
            "retrocausality": "backward requirement planning; no retrocausal influence",
            "cosmic_infrastructure": "Landauer and light-speed limits reported; no energy harvesting",
            "absolute_unbounded": "every operation is bounded and reports its limits",
            "physical_materialization": "BOM, assembly plan, energy/cost estimates, and digital twin",
            "self_manufacturing": "bootstrap plan exists; no printer, robot, feedstock, facility, or verified interface",
            "sovereign_economy": "unit economics and break-even model; no capital or revenue",
            "weakness_closure": "known gaps are mapped to a mitigation and a next action",
            "zero_weakness": "no zero-weakness guarantee; residual physical and economic dependencies remain",
        }
        items = []
        for requirement in REQUIREMENTS:
            status = requirement["status"]
            items.append(
                {
                    "id": requirement["id"],
                    "need": requirement["need"],
                    "status": status,
                    "nearest": nearest.get(
                        requirement["id"],
                        "implemented evidence" if status == "met" else requirement["note"],
                    ),
                    "blocker": None if status == "met" else requirement["note"],
                    "next_action": (
                        "keep the measured capability and its tests"
                        if status == "met"
                        else "retain the bounded analog; the literal gap is named in the contract"
                    ),
                }
            )
        all_items = items
        counts = {"met": 0, "partial": 0, "false": 0}
        for item in all_items:
            counts[item["status"]] += 1
        return {
            "items": all_items,
            "summary": {
                **counts,
                "total": len(all_items),
                "fraction_met": round(counts["met"] / len(all_items), 4),
                "zero_weakness_claim": False,
                "physical_sovereignty": False,
            },
            "residual_risks": [
                "no actuator, sensor, or physical effect is verified",
                "no fabrication facility, feedstock, or energy contract is present",
                "no capital, customer, or payment channel is present",
                "supplier, legal, safety, and maintenance dependencies remain",
            ],
            "weakness_policy": (
                "Every known gap is mapped to a bounded mitigation and a next action. "
                "This is not a claim that the system has no weaknesses."
            ),
            "note": (
                "The closest honest implementation of the materialization demand: "
                "a buildable design and a closure ledger, not a physical body."
            ),
        }

    def archetypes(self) -> dict[str, Any]:
        return {
            "archetypes": [
                {
                    "id": name,
                    "name": value["name"],
                    "components": len(value["components"]),
                    "tools": value["tools"],
                    "standards": value["standards"],
                }
                for name, value in ARCHETYPES.items()
            ],
            "note": "templates are engineering starting points, not certified designs",
        }
