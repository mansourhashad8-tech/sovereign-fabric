"""A demand ledger distilled from the visible conversation.

Every contract requirement is kept, plus the earlier build commitments that are
not represented as separate contract items. Each entry names the literal ask,
the closest real implementation, the blocker, and the next action. The ledger
does not turn a partial or false literal claim into a success.
"""

from __future__ import annotations

from typing import Any

from .contract import REQUIREMENTS
from .materialization import Materialization

SOURCE_LABELS = {
    "protocol_1": "external guardianship and self-evolution protocol",
    "protocol_2": "materialization and sovereign-economy protocol",
    "protocol_3": "absolute sovereignty and ontological-perfection protocol",
    "prior_build": "earlier build commitments in this workspace",
    "legacy_external": "work preserved outside this repository",
}

_SOURCE_MAP = {
    "external_guardianship": "protocol_1",
    "unified_fabric": "protocol_1",
    "continuous_evolution": "protocol_1",
    "broad_capabilities": "protocol_1",
    "instant_absorption": "protocol_1",
    "retrieval_graph_vectors": "protocol_1",
    "multimodal_quantum": "protocol_1",
    "self_generating_code": "protocol_1",
    "hyper_kernel": "protocol_1",
    "functional_self_model": "protocol_1",
    "sovereign_will": "protocol_1",
    "ontological_evolution": "protocol_1",
    "digital_physical": "protocol_1",
    "cosmic_protocol": "protocol_1",
    "temporal_prediction": "protocol_1",
    "retrocausality": "protocol_1",
    "cosmic_infrastructure": "protocol_1",
    "runtime_settings": "protocol_1",
    "feedback_calibration": "protocol_1",
    "unified_context": "protocol_1",
    "self_directed_practice": "protocol_1",
    "criterion_applicability": "protocol_1",
    "external_media_orchestration": "protocol_1",
    "no_false_claims": "protocol_1",
    "security_invariants": "protocol_1",
    "openness_ci": "protocol_1",
    "absolute_unbounded": "protocol_1",
    "physical_materialization": "protocol_2",
    "self_manufacturing": "protocol_2",
    "sovereign_economy": "protocol_2",
    "weakness_closure": "protocol_2",
    "zero_weakness": "protocol_2",
    "capability_fusion": "protocol_3",
    "absolute_sovereignty": "protocol_3",
    "dynamic_perfection": "protocol_3",
    "cosmic_determinism": "protocol_3",
    "ontological_perfection": "protocol_3",
    "no_failure_no_delay": "protocol_3",
}

_LITERAL_CLAIMS = {
    "multimodal_quantum",
    "hyper_kernel",
    "digital_physical",
    "self_manufacturing",
    "retrocausality",
    "cosmic_infrastructure",
    "absolute_unbounded",
    "zero_weakness",
    "absolute_sovereignty",
    "cosmic_determinism",
    "ontological_perfection",
    "no_failure_no_delay",
}

_PRIOR = [
    {
        "id": "prior_arabic_retrieval",
        "source": "prior_build",
        "request": "Arabic input and Arabic retrieval should work",
        "literal_claim": False,
        "status": "met",
        "closest": "Arabic normalization, light stemming, and hybrid BM25/vector retrieval",
        "evidence": ["arabic.py", "vectors.py", "ranking.py"],
        "blocker": None,
        "next_action": "add morphology or NER only if a measured task needs it",
    },
    {
        "id": "prior_capability_breadth",
        "source": "prior_build",
        "request": "do not specialize in one domain",
        "literal_claim": False,
        "status": "met",
        "closest": "a bounded multi-domain toolbox with 129 active capabilities",
        "evidence": ["toolbox.py", "toolbox_ext.py", "extras.py"],
        "blocker": "the library is broad but not omniscient",
        "next_action": "add capabilities from measured demand, not from a count target",
    },
    {
        "id": "prior_dashboard",
        "source": "prior_build",
        "request": "see the system state in one place",
        "literal_claim": False,
        "status": "met",
        "closest": "self-contained dashboard over live report, security, and self-model",
        "evidence": ["dashboard.py", "/dashboard"],
        "blocker": None,
        "next_action": "add a panel only when it exposes a new measured signal",
    },
    {
        "id": "prior_api_hardening",
        "source": "prior_build",
        "request": "secure API and reject malformed or oversized input",
        "literal_claim": False,
        "status": "met",
        "closest": "optional API key, rate limit, body cap, security headers, DAST tests",
        "evidence": ["guard.py", "tests/test_dast.py", "security.py"],
        "blocker": None,
        "next_action": "keep the public GET surface and the guarded write surface separate",
    },
    {
        "id": "prior_openness_sbom",
        "source": "prior_build",
        "request": "prove the work is open, licensed, and audited",
        "literal_claim": False,
        "status": "met",
        "closest": "SHA-256 manifest, CycloneDX SBOM, strict audit, public CI",
        "evidence": ["OPENNESS_MANIFEST.json", "sbom.cdx.json", ".github/workflows/"],
        "blocker": None,
        "next_action": "regenerate after every source change",
    },
    {
        "id": "prior_expert_layer",
        "source": "prior_build",
        "request": "ask another AI when the local system is not enough",
        "literal_claim": False,
        "status": "partial",
        "closest": "OpenAI-compatible expert client with verification gate",
        "evidence": ["expert.py", "acquire.py", "/expert/ask"],
        "blocker": "the Groq key returns 401; no other expert key is configured",
        "next_action": "replace the key or configure OPENAI_BASE_URL",
    },
    {
        "id": "prior_quantum_media",
        "source": "prior_build",
        "request": "use quantum and multimodal tools",
        "literal_claim": False,
        "status": "partial",
        "closest": "classical statevector simulator and image/audio header parsing",
        "evidence": ["quantum.py", "media.py"],
        "blocker": "no quantum hardware, OCR, vision, or transcription backend",
        "next_action": "attach a real backend only with measured output and provenance",
    },
    {
        "id": "prior_immunity_collective",
        "source": "prior_build",
        "request": "self-protect and share lessons without leaking data",
        "literal_claim": False,
        "status": "partial",
        "closest": "bounded immunity statistics and manual anonymized lesson exchange",
        "evidence": ["immunity.py", "collective.py", "autonomy.py"],
        "blocker": "no federated learning, no automatic patch, no network exchange",
        "next_action": "keep lessons as data and require a separate code-admission gate",
    },
    {
        "id": "prior_settings_calibration",
        "source": "prior_build",
        "request": "change its own settings safely and learn from outcomes",
        "literal_claim": False,
        "status": "met",
        "closest": "five allowlisted settings with bounds and prequential Brier score",
        "evidence": ["settings.py", "feedback.py", "selfmodel.py"],
        "blocker": "safety thresholds and admission rules stay fixed",
        "next_action": "tune only from measured skill, never from preference",
    },
    {
        "id": "prior_remote_orchestration",
        "source": "prior_build",
        "request": "run real work outside the local sandbox",
        "literal_claim": False,
        "status": "met",
        "closest": "probed GitHub Actions dispatch with observed runs and quality gates",
        "evidence": ["providers.py", "orchestration.py", "remote-task.yml"],
        "blocker": "HF inference is blocked by credits; Groq is expired",
        "next_action": "add another verified heavy provider when credentials exist",
    },
    {
        "id": "prior_materialization",
        "source": "prior_build",
        "request": "turn a physical idea into a buildable plan",
        "literal_claim": False,
        "status": "partial",
        "closest": "BOM, assembly plan, energy/cost estimates, digital twin",
        "evidence": ["materialization.py", "/materialization/blueprint"],
        "blocker": "no printer, robot, feedstock, facility, or verified actuator",
        "next_action": "verify a fabrication cell before any build claim",
    },
    {
        "id": "prior_sovereignty_fusion",
        "source": "prior_build",
        "request": "join all capabilities into one coherent whole",
        "literal_claim": False,
        "status": "partial",
        "closest": "ten-domain functional fusion with a sovereignty audit",
        "evidence": ["sovereignty.py", "/sovereignty/fusion"],
        "blocker": "functional composition is not metaphysical unity",
        "next_action": "keep the audit explicit and add evidence per domain",
    },
    {
        "id": "prior_unified_transformation",
        "source": "prior_build",
        "request": "make one request drive the whole system end to end",
        "literal_claim": False,
        "status": "met",
        "closest": "one trace across intent, plan, digital/remote/material execution, validation, and ledger",
        "evidence": ["transformation.py", "/transform"],
        "blocker": None,
        "next_action": "keep the trace and the explicit non-claims",
    },
    {
        "id": "prior_legacy_commerce",
        "source": "legacy_external",
        "request": "earn real value and settle it without gas",
        "literal_claim": False,
        "status": "external",
        "closest": "archived ZK settlement and commerce-engine work in another repository",
        "evidence": ["archive-2026-11-24-commerce-engine.md"],
        "blocker": "not this repository; the fork unit has no market value and the beneficiary holds no funds",
        "next_action": "reopen that repository separately; do not merge its claims into this contract",
    },
]


class DemandLedger:
    def __init__(self, store=None) -> None:
        self.store = store

    def items(self) -> list[dict[str, Any]]:
        closure = Materialization(self.store).closure()
        by_id = {item["id"]: item for item in closure["items"]}
        items = []
        for requirement in REQUIREMENTS:
            item = by_id[requirement["id"]]
            items.append(
                {
                    "id": requirement["id"],
                    "source": _SOURCE_MAP.get(requirement["id"], "prior_build"),
                    "source_label": SOURCE_LABELS[_SOURCE_MAP.get(requirement["id"], "prior_build")],
                    "request": requirement["need"],
                    "literal_claim": requirement["id"] in _LITERAL_CLAIMS,
                    "status": requirement["status"],
                    "closest": item["nearest"],
                    "evidence": list(requirement.get("evidence", [])),
                    "blocker": item["blocker"],
                    "next_action": item["next_action"],
                }
            )
        for prior in _PRIOR:
            items.append(
                {
                    **prior,
                    "source_label": SOURCE_LABELS[prior["source"]],
                    "evidence": list(prior.get("evidence", [])),
                }
            )
        return items

    def report(self, source: str | None = None, status: str | None = None) -> dict[str, Any]:
        items = self.items()
        if source:
            items = [item for item in items if item["source"] == source]
        if status:
            items = [item for item in items if item["status"] == status]
        counts = {"met": 0, "partial": 0, "false": 0, "external": 0}
        for item in items:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        literal = [item for item in items if item["literal_claim"]]
        literal_met = sum(1 for item in literal if item["status"] == "met")
        sources = {}
        for item in items:
            sources[item["source"]] = sources.get(item["source"], 0) + 1
        return {
            "items": items,
            "summary": {
                **counts,
                "total": len(items),
                "literal_claims": len(literal),
                "literal_claims_met": literal_met,
                "all_literal_claims_met": False,
                "sources": sources,
            },
            "unresolved": [item for item in items if item["status"] != "met"],
            "note": (
                "Every visible protocol demand and every earlier build commitment is mapped "
                "to the closest real implementation. Literal absolute claims stay false."
            ),
        }

    def find(self, demand_id: str) -> dict[str, Any] | None:
        for item in self.items():
            if item["id"] == demand_id:
                return item
        return None
