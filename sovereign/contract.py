"""A requirement contract distilled from the whole conversation.

This is a curated ledger, not a transcript. Each item names the user need, the
implemented evidence, and an honest status: met, partial, or false. False items
are literal claims the system refuses, not missing endpoints.
"""

from __future__ import annotations

from typing import Any

from .cosmic import CosmicProtocol
from .metacurriculum import MetaCurriculum
from .selfhood import Selfhood
from .settings import Settings

REQUIREMENTS: list[dict[str, Any]] = [
    {
        "id": "external_guardianship",
        "need": "consult external sources and experts instead of relying only on itself",
        "status": "met",
        "evidence": ["guardians.py", "expert.py", "/consult", "/absorb"],
        "note": "22 source adapters; dead sources degrade the result",
    },
    {
        "id": "unified_fabric",
        "need": "one fabric for knowledge, capabilities, events, and execution",
        "status": "met",
        "evidence": ["store.py", "evolution.py", "/evolve", "/ask"],
        "note": "SQLite store plus one evolution cycle",
    },
    {
        "id": "continuous_evolution",
        "need": "keep improving without waiting for a new command",
        "status": "met",
        "evidence": ["loop.py", "metacurriculum.py"],
        "note": "bounded scheduler and self-directed practice",
    },
    {
        "id": "broad_capabilities",
        "need": "do not specialize in one domain",
        "status": "met",
        "evidence": ["capabilities.py", "toolbox.py", "toolbox_ext.py"],
        "note": "many built-in domains; not omniscient",
    },
    {
        "id": "instant_absorption",
        "need": "absorb a new unit or tool immediately",
        "status": "met",
        "evidence": ["absorption.py", "/absorb"],
        "note": "write to the same store the planner reads",
    },
    {
        "id": "retrieval_graph_vectors",
        "need": "dynamic knowledge graph, vector retrieval, and context",
        "status": "met",
        "evidence": ["ranking.py", "semantic.py", "context.py"],
        "note": "hybrid retrieval and depth-1 graph expansion",
    },
    {
        "id": "multimodal_quantum",
        "need": "multimodal models and quantum simulators",
        "status": "false",
        "evidence": [],
        "note": "no multimodal model or quantum backend is configured",
    },
    {
        "id": "self_generating_code",
        "need": "generate new capabilities when a goal is blocked",
        "status": "partial",
        "evidence": ["synthesis.py", "acquire.py", "blueprints.py"],
        "note": "bounded synthesis with a subprocess gate, not arbitrary self-rewrite",
    },
    {
        "id": "hyper_kernel",
        "need": "quantum-like memory and near-light internal signaling",
        "status": "partial",
        "evidence": ["hyper.py"],
        "note": "classical HRR memory and in-process bus; no quantum hardware",
    },
    {
        "id": "functional_self_model",
        "need": "functional self-awareness of role, state, and limits",
        "status": "met",
        "evidence": ["selfhood.py", "/selfhood"],
        "note": "model of own state; not subjective experience",
    },
    {
        "id": "sovereign_will",
        "need": "act without waiting for orders",
        "status": "partial",
        "evidence": ["selfhood.py", "metacurriculum.py"],
        "note": "one bounded internal action; no independent goals or values",
    },
    {
        "id": "ontological_evolution",
        "need": "redefine its own identity continuously",
        "status": "partial",
        "evidence": ["selfhood.py", "/selfhood/definition"],
        "note": "versioned self-description; invariants stay fixed",
    },
    {
        "id": "digital_physical",
        "need": "affect the physical world as well as the digital one",
        "status": "false",
        "evidence": ["selfhood.py", "/selfhood/reality"],
        "note": "no sensors, actuators, or physical bridge",
    },
    {
        "id": "cosmic_protocol",
        "need": "shape reality, predict futures, and use cosmic infrastructure",
        "status": "partial",
        "evidence": ["cosmic.py", "/cosmic"],
        "note": "2/5 functional analogs; 0/5 literal claims",
    },
    {
        "id": "temporal_prediction",
        "need": "evaluate many future scenarios before acting",
        "status": "met",
        "evidence": ["cosmic.py", "/cosmic/predict"],
        "note": "seeded Monte Carlo over a known chain; capped and measured",
    },
    {
        "id": "retrocausality",
        "need": "make the result cause its own antecedents",
        "status": "false",
        "evidence": ["cosmic.py", "/cosmic/backward"],
        "note": "backward planning only; no retrocausality",
    },
    {
        "id": "cosmic_infrastructure",
        "need": "use the universe's physical laws as compute and energy",
        "status": "false",
        "evidence": ["cosmic.py", "/cosmic/infrastructure"],
        "note": "no energy harvesting; Landauer and light-speed limits are reported",
    },
    {
        "id": "runtime_settings",
        "need": "change its own operating settings safely",
        "status": "met",
        "evidence": ["settings.py", "/settings"],
        "note": "five allowlisted parameters, hard bounds, audit, reset",
    },
    {
        "id": "feedback_calibration",
        "need": "learn from outcomes and measure its own predictions",
        "status": "met",
        "evidence": ["feedback.py", "selfmodel.py", "/self/calibration"],
        "note": "smoothed feedback and prequential Brier score",
    },
    {
        "id": "unified_context",
        "need": "join everything into one usable context",
        "status": "met",
        "evidence": ["context.py", "/context"],
        "note": "knowledge, capabilities, events, graph, settings",
    },
    {
        "id": "self_directed_practice",
        "need": "choose what to improve and measure the result",
        "status": "met",
        "evidence": ["metacurriculum.py", "/curriculum/meta"],
        "note": "weak rate plus uncertainty; one bounded practice cycle",
    },
    {
        "id": "criterion_applicability",
        "need": "do not fail a local transform for external-retrieval criteria",
        "status": "met",
        "evidence": ["validator.py", "models.py", "metacurriculum.py"],
        "note": "explicit local_transform only; default local-only knowledge claims still fail",
    },
    {
        "id": "external_media_orchestration",
        "need": "direct professional external media instead of relying on the local environment",
        "status": "met",
        "evidence": [
            "providers.py",
            "orchestration.py",
            "quality.py",
            ".github/workflows/remote-task.yml",
            "https://github.com/mansourhashad8-tech/sovereign-fabric/actions/runs/45720322520",
        ],
        "note": "GitHub Actions dispatch observed success; HF Hub ready; HF inference blocked by credits; Groq key expired; account creation is not automated",
    },
    {
        "id": "no_false_claims",
        "need": "never round a failure up to a success",
        "status": "met",
        "evidence": ["protocol.py", "validator.py", "tests/"],
        "note": "result-first protocol and overclaim detector",
    },
    {
        "id": "security_invariants",
        "need": "no custody, no private keys, no user gas",
        "status": "met",
        "evidence": ["guard.py", "security.py", "tests/"],
        "note": "security flags are system invariants, not preferences",
    },
    {
        "id": "openness_ci",
        "need": "prove the work is open and audited",
        "status": "met",
        "evidence": ["OPENNESS_MANIFEST.json", "SECURITY_DISCLOSURE.md", ".github/workflows/"],
        "note": "strict audit and CI",
    },
    {
        "id": "absolute_unbounded",
        "need": "have literally infinite, unconstrained capability",
        "status": "false",
        "evidence": [],
        "note": "every operation is bounded and reports its limits",
    },
]


def audit(engine) -> dict[str, Any]:
    profile = Selfhood(engine).model.profile()
    selfhood = Selfhood(engine).validate()
    cosmic = CosmicProtocol(engine).validate()
    settings = Settings(engine.store).snapshot()
    meta = MetaCurriculum(engine).table(scenarios=20)
    counts = {"met": 0, "partial": 0, "false": 0}
    for item in REQUIREMENTS:
        counts[item["status"]] += 1
    return {
        "requirements": REQUIREMENTS,
        "coverage": {
            **counts,
            "total": len(REQUIREMENTS),
            "fraction_met": round(counts["met"] / len(REQUIREMENTS), 4),
        },
        "gaps": [
            {"id": item["id"], "status": item["status"], "note": item["note"]}
            for item in REQUIREMENTS
            if item["status"] != "met"
        ],
        "live": {
            "capabilities": profile["capabilities"]["total"],
            "knowledge_units": profile["knowledge_units"],
            "sources": len(profile["sources"]),
            "cycles": profile["cycles"]["total"],
            "settings_revision": settings["revision"],
            "selfhood_functional": selfhood["met"],
            "selfhood_literal": 0,
            "cosmic_functional": cosmic["functional_met"],
            "cosmic_literal": cosmic["literal_met"],
            "meta_goals": len(meta),
        },
        "note": (
            "Curated from the conversation. 'false' means the literal claim is "
            "refused, not that an endpoint is missing. The contract is a map, "
            "not proof of consciousness or infinite capability."
        ),
    }
