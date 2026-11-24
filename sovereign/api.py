from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .absorption import absorb
from .evolution import EvolutionEngine
from .models import Evidence, KnowledgeUnit
from .store import FabricStore


class ConsultRequest(BaseModel):
    query: str
    limit: int = 5
    sources: list[str] | None = None


class AbsorbRequest(ConsultRequest):
    pass


class SynthesizeRequest(BaseModel):
    name: str
    description: str
    inputs: list[str]
    outputs: list[str]
    spec: dict[str, Any]
    examples: list[Any]


class RollbackRequest(BaseModel):
    name: str


class EvolveRequest(BaseModel):
    request: str
    goal_type: str = "markdown"
    initial: list[str] = Field(default_factory=lambda: ["text"])
    text: str | None = None
    sources: list[str] | None = None
    limit: int = 5
    synthesize: dict[str, Any] | None = None
    budget_s: float = 5.0


class ValidateRequest(BaseModel):
    subject: str
    claims: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


def _unit_dict(unit: KnowledgeUnit) -> dict[str, Any]:
    return {
        "id": unit.id,
        "title": unit.title,
        "summary": unit.summary,
        "concepts": list(unit.concepts),
        "tags": list(unit.tags),
        "provenance": {
            "source": unit.provenance.source,
            "url": unit.provenance.url,
            "retrieved_at": unit.provenance.retrieved_at,
            "license": unit.provenance.license,
            "confidence": unit.provenance.confidence,
        },
    }


def create_app(store_path: str = ":memory:") -> FastAPI:
    store = FabricStore(store_path)
    engine = EvolutionEngine(store)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        store.close()

    app = FastAPI(title="Sovereign Fabric", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.engine = engine

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "name": "sovereign-fabric",
            "note": "honest self-evolving fabric; no claim is reported without evidence",
            "endpoints": [
                "GET /health",
                "GET /guardians",
                "POST /consult",
                "POST /absorb",
                "GET /knowledge/search",
                "GET /capabilities",
                "POST /capabilities/rollback",
                "POST /synthesize",
                "POST /evolve",
                "GET /cycles",
                "GET /failures",
                "POST /validate",
            ],
        }

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "knowledge_units": store.count_knowledge(),
            "active_capabilities": len(engine.registry.list_active()),
            "guardians": engine.guardians.names(),
        }

    @app.get("/guardians")
    def guardians() -> dict[str, Any]:
        return {"guardians": engine.guardians.names()}

    @app.post("/consult")
    def consult(body: ConsultRequest) -> dict[str, Any]:
        result = engine.guardians.consult(body.query, body.limit, body.sources)
        return {
            "query": result.query,
            "sources": result.sources,
            "units": [_unit_dict(unit) for unit in result.units],
        }

    @app.post("/absorb")
    def absorb_endpoint(body: AbsorbRequest) -> dict[str, Any]:
        result = engine.guardians.consult(body.query, body.limit, body.sources)
        count = absorb(store, result.units)
        return {"query": result.query, "sources": result.sources, "absorbed": count}

    @app.get("/knowledge/search")
    def search(q: str, k: int = 5) -> dict[str, Any]:
        hits = store.search_knowledge(q, k)
        return {
            "query": q,
            "hits": [
                {"score": round(score, 4), **_unit_dict(unit)} for unit, score in hits
            ],
        }

    @app.get("/capabilities")
    def capabilities() -> dict[str, Any]:
        return {
            "capabilities": [
                {
                    "name": cap.name,
                    "version": cap.version,
                    "status": cap.status,
                    "kind": cap.kind,
                    "inputs": list(cap.inputs),
                    "outputs": list(cap.outputs),
                    "description": cap.description,
                }
                for cap in store.list_capabilities()
            ]
        }

    @app.post("/capabilities/rollback")
    def rollback(body: RollbackRequest) -> dict[str, Any]:
        active = engine.registry.rollback(body.name)
        return {
            "name": body.name,
            "active": None
            if active is None
            else {"version": active.version, "status": active.status},
        }

    @app.post("/synthesize")
    def synthesize(body: SynthesizeRequest) -> dict[str, Any]:
        result = engine.synthesizer.synthesize(
            name=body.name,
            description=body.description,
            inputs=tuple(body.inputs),
            outputs=tuple(body.outputs),
            spec=body.spec,
            examples=body.examples,
        )
        return {
            "admitted": result.admitted,
            "reason": result.reason,
            "passed": result.passed,
            "failed": result.failed,
            "failures": result.failures,
            "version": result.capability.version if result.capability else None,
        }

    @app.post("/evolve")
    def evolve(body: EvolveRequest) -> dict[str, Any]:
        cycle = engine.evolve(
            body.request,
            goal_type=body.goal_type,
            initial=tuple(body.initial),
            text=body.text,
            sources=body.sources,
            limit=body.limit,
            synthesize=body.synthesize,
            budget_s=body.budget_s,
        )
        return {
            "request": cycle.request,
            "ok": cycle.ok,
            "plan": [
                {"capability": step.capability, "version": step.version}
                for step in cycle.plan.steps
            ],
            "plan_solved": cycle.plan.solved,
            "execution": cycle.execution,
            "absorbed": cycle.absorbed,
            "proposals": cycle.proposals,
            "sources": cycle.consultation.sources,
            "synthesis": None
            if cycle.synthesis is None
            else {
                "admitted": cycle.synthesis.admitted,
                "reason": cycle.synthesis.reason,
                "passed": cycle.synthesis.passed,
                "failed": cycle.synthesis.failed,
            },
            "validation": {
                "passed": cycle.validation.passed,
                "scores": cycle.validation.scores,
                "failures": cycle.validation.failures,
                "overclaims": cycle.validation.overclaims,
                "notes": cycle.validation.notes,
            },
            "duration_s": round(cycle.duration_s, 4),
        }

    @app.get("/cycles")
    def cycles(limit: int = 20) -> dict[str, Any]:
        return {"cycles": store.list_events("cycle", limit)}

    @app.get("/failures")
    def failures(limit: int = 100) -> dict[str, Any]:
        return {"failure_memo": store.memo_entries(limit)}

    @app.post("/validate")
    def validate(body: ValidateRequest) -> dict[str, Any]:
        evidence = [
            Evidence(
                kind=str(item.get("kind", "")),
                detail=str(item.get("detail", "")),
                ref=str(item.get("ref", "")),
            )
            for item in body.evidence
        ]
        report = engine.validator.validate(body.subject, body.claims, evidence, body.context)
        return {
            "subject": report.subject,
            "passed": report.passed,
            "scores": report.scores,
            "failures": report.failures,
            "overclaims": report.overclaims,
            "notes": report.notes,
        }

    return app


app = create_app()
