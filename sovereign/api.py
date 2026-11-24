from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .absorption import absorb
from .curriculum import Curriculum
from .dashboard import DASHBOARD_HTML
from .evolution import EvolutionEngine
from .execution import ExecutionEngine, HotCache, Prefetcher, RemoteExecutor, benchmark
from .models import Evidence, KnowledgeUnit
from .redteam import audit
from .report import render_report, system_report
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
    auto_extend: bool = False
    max_attempts: int = 1


class ValidateRequest(BaseModel):
    subject: str
    claims: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class AcquireRequest(BaseModel):
    name: str
    description: str
    inputs: list[str] = Field(default_factory=lambda: ["text"])
    outputs: list[str] = Field(default_factory=lambda: ["out"])
    examples: list[Any]
    rounds: int = 2


class CurriculumRequest(BaseModel):
    iterations: int = 3
    sources: list[str] | None = None
    budget_s: float = 10.0
    auto_extend: bool = True


class BatchRequest(BaseModel):
    capability: str
    payloads: list[Any]
    mode: str = "auto"
    workers: int | None = None


class WarmRequest(BaseModel):
    queries: list[str]


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
    execution = ExecutionEngine()
    cache = HotCache()
    prefetcher = Prefetcher(cache)
    remote = RemoteExecutor()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        store.close()

    app = FastAPI(title="Sovereign Fabric", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.engine = engine
    app.state.execution = execution
    app.state.cache = cache

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "name": "sovereign-fabric",
            "note": "honest self-evolving fabric; no claim is reported without evidence",
            "dashboard": "/dashboard",
            "endpoints": [
                "GET /health",
                "GET /dashboard",
                "GET /guardians",
                "POST /consult",
                "POST /absorb",
                "GET /knowledge/search",
                "GET /capabilities",
                "POST /capabilities/rollback",
                "POST /synthesize",
                "POST /evolve",
                "POST /curriculum",
                "GET /redteam",
                "POST /execute/batch",
                "GET /execute/benchmark",
                "GET /cache/stats",
                "POST /cache/warm",
                "GET /remote/status",
                "GET /report",
                "GET /report.md",
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
        cache_key = ("search", q, k)
        hits = cache.get(cache_key)
        qvec, prefetch_hit = prefetcher.embedding(q)
        if hits is None:
            hits = store.search_knowledge(q, k, qvec=qvec)
            cache.put(cache_key, hits)
        return {
            "query": q,
            "prefetch_hit": prefetch_hit,
            "hits": [
                {"score": round(score, 4), **_unit_dict(unit)} for unit, score in hits
            ],
        }

    @app.get("/knowledge/graph")
    def knowledge_graph(node: str, rel: str | None = None, depth: int = 1) -> dict[str, Any]:
        return store.graph(node, rel=rel, depth=depth)

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
        prefetcher.prefetch(body.request)
        cycle = engine.evolve(
            body.request,
            goal_type=body.goal_type,
            initial=tuple(body.initial),
            text=body.text,
            sources=body.sources,
            limit=body.limit,
            synthesize=body.synthesize,
            budget_s=body.budget_s,
            auto_extend=body.auto_extend,
            max_attempts=body.max_attempts,
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
            "extensions": cycle.extensions,
            "attempts": cycle.attempts,
            "diagnosis": cycle.diagnosis,
            "duration_s": round(cycle.duration_s, 4),
        }

    @app.get("/experts")
    def experts() -> dict[str, Any]:
        return {
            "experts": [
                {"name": expert.name, "model": getattr(expert, "model", None)}
                for expert in engine.experts
            ]
        }

    @app.post("/acquire")
    def acquire(body: AcquireRequest) -> dict[str, Any]:
        result = engine.acquirer.acquire(
            body.name,
            body.description,
            tuple(body.inputs),
            tuple(body.outputs),
            body.examples,
            rounds=body.rounds,
        )
        return {
            "admitted": result.admitted,
            "reason": result.reason,
            "source": result.source,
            "capability": result.capability.name if result.capability else None,
            "attempts": result.attempts,
        }

    @app.post("/curriculum")
    def curriculum(body: CurriculumRequest) -> dict[str, Any]:
        return {
            "results": Curriculum(engine).run(
                iterations=body.iterations,
                sources=body.sources,
                budget_s=body.budget_s,
                auto_extend=body.auto_extend,
            )
        }

    @app.get("/redteam")
    def redteam() -> dict[str, Any]:
        return audit(engine.validator)

    @app.post("/execute/batch")
    def execute_batch(body: BatchRequest) -> dict[str, Any]:
        if len(body.payloads) > 10000:
            raise HTTPException(status_code=413, detail="batch limited to 10000 payloads")
        result = execution.run_capability(
            engine.registry,
            body.capability,
            body.payloads,
            mode=body.mode,
            workers=body.workers,
        )
        return result.to_dict()

    @app.get("/execute/benchmark")
    def execute_benchmark(
        n: int = 100000,
        capability: str = "text.tokenize",
        mode: str = "processes",
        workers: int | None = None,
        workload: str = "tokenize",
        iterations: int = 20000,
    ) -> dict[str, Any]:
        return benchmark(
            n=n,
            capability=capability,
            mode=mode,
            workers=workers,
            workload=workload,
            iterations=iterations,
        )

    @app.get("/cache/stats")
    def cache_stats() -> dict[str, Any]:
        return {**cache.stats_dict(), "prefetch": prefetcher.stats_dict()}

    @app.post("/cache/warm")
    def cache_warm(body: WarmRequest) -> dict[str, Any]:
        warmed = sum(prefetcher.prefetch(query) for query in body.queries)
        return {"warmed": warmed, **prefetcher.stats_dict()}

    @app.get("/remote/status")
    def remote_status() -> dict[str, Any]:
        return {"available": remote.available, "configured": bool(remote.endpoint)}

    def _report(
        query: str,
        goal_type: str,
        budget_s: float,
        benchmark_n: int,
        sources: str | None,
        benchmark_mode: str,
    ) -> dict[str, Any]:
        selected = [s for s in sources.split(",") if s] if sources else None
        return system_report(
            engine,
            query=query,
            goal_type=goal_type,
            sources=selected,
            budget_s=budget_s,
            benchmark_n=benchmark_n,
            benchmark_mode=benchmark_mode,
        )

    @app.get("/report")
    def report(
        query: str = "retrieval augmented generation",
        goal_type: str = "markdown",
        budget_s: float = 15.0,
        benchmark_n: int = 200,
        sources: str | None = None,
        benchmark_mode: str = "processes",
    ) -> dict[str, Any]:
        return _report(query, goal_type, budget_s, benchmark_n, sources, benchmark_mode)

    @app.get("/report.md", response_class=PlainTextResponse)
    def report_markdown(
        query: str = "retrieval augmented generation",
        goal_type: str = "markdown",
        budget_s: float = 15.0,
        benchmark_n: int = 200,
        sources: str | None = None,
        benchmark_mode: str = "processes",
    ) -> str:
        return render_report(
            _report(query, goal_type, budget_s, benchmark_n, sources, benchmark_mode)
        )

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard() -> str:
        return DASHBOARD_HTML

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
