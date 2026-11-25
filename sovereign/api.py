from __future__ import annotations

import re
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .absorption import absorb
from .autonomy import assess, reward_ledger
from .capabilities import CapabilityError
from .collective import collective_status, export_bundle, import_bundle
from .curriculum import Curriculum
from .brief import build_brief
from .dashboard import DASHBOARD_HTML
from .diagnostics import diagnose
from .evidence import verify_claim
from .feedback import feedback_scores, feedback_summary, record_feedback
from .evolution import EvolutionEngine
from .guard import ApiKey, RateLimiter, max_body_bytes, security_headers
from .immunity import ImmuneSystem
from .intent import parse_intent
from .loop import EvolutionLoop
from .mastery import Mastery
from .metrics import Metrics
from .optimizer import Optimizer
from .pathfinder import operators_from
from .protocol import BANNED_PHRASES, DeterministicProtocol, audit_language
from .pipeline import run_pipeline
from .repair import repair
from .execution import ExecutionEngine, HotCache, Prefetcher, RemoteExecutor, benchmark
from .models import Evidence, KnowledgeUnit
from .redteam import audit
from .properties import check_capabilities
from .report import render_report, system_report
from .security import audit as security_audit, cyclonedx_sbom, disclosure_markdown
from .selfmodel import SelfModel
from .store import FabricStore
from .vectors import cosine, embed

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class ConsultRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=50)
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
    request: str = Field(min_length=1, max_length=2000)
    goal_type: str = "markdown"
    initial: list[str] = Field(default_factory=lambda: ["text"])
    text: str | None = Field(default=None, max_length=20000)
    sources: list[str] | None = None
    limit: int = Field(default=5, ge=1, le=50)
    synthesize: dict[str, Any] | None = None
    budget_s: float = 5.0
    auto_extend: bool = False
    max_attempts: int = 1


class ValidateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=500)
    claims: list[str] = Field(default_factory=list, max_length=50)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class AcquireRequest(BaseModel):
    name: str
    description: str
    inputs: list[str] = Field(default_factory=lambda: ["text"])
    outputs: list[str] = Field(default_factory=lambda: ["out"])
    examples: list[Any]
    rounds: int = 2


class BriefRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)
    sources: list[str] | None = None
    lang: str = "en"
    deadline_s: float = Field(default=12.0, gt=0, le=120)


class InvokeRequest(BaseModel):
    capability: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class PipelineStep(BaseModel):
    capability: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] | None = None


class PipelineRequest(BaseModel):
    steps: list[PipelineStep] = Field(min_length=1, max_length=20)


class BatchInvokeCall(BaseModel):
    capability: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class BatchInvokeRequest(BaseModel):
    calls: list[BatchInvokeCall] = Field(min_length=1, max_length=20)


class FeedbackRequest(BaseModel):
    capability: str = Field(min_length=1, max_length=100)
    rating: int = Field(ge=-1, le=1)
    note: str = Field(default="", max_length=500)
    request_id: str | None = Field(default=None, max_length=64)


class ExpertAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    system: str = Field(
        default="Answer concisely. Do not claim to have run code or checked sources.",
        max_length=2000,
    )


class ClaimRequest(BaseModel):
    claim: str = Field(min_length=1, max_length=2000)
    k: int = 5


class AskRequest(BaseModel):
    request: str = Field(min_length=1, max_length=2000)
    budget_s: float = 10.0
    sources: list[str] | None = None
    auto_extend: bool = True


class ProtocolRequest(BaseModel):
    request: str = Field(min_length=1, max_length=2000)
    goal_type: str | None = None
    initial: list[str] | None = None
    text: str | None = Field(default=None, max_length=20000)
    sources: list[str] | None = None
    synthesize: dict[str, Any] | None = None
    budget_s: float = Field(default=5.0, gt=0, le=60)
    max_alternatives: int = Field(default=4, ge=1, le=4)


class LanguageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


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
    optimizer = Optimizer(engine.registry)
    immune = ImmuneSystem(store)
    protocol = DeterministicProtocol(engine)
    loop = EvolutionLoop(engine, interval_s=60.0, immune=immune)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        store.close()

    app = FastAPI(title="Sovereign Fabric", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.engine = engine
    app.state.execution = execution
    app.state.cache = cache
    app.state.optimizer = optimizer
    app.state.immune = immune
    app.state.protocol = protocol
    app.state.loop = loop
    api_key = ApiKey()
    limiter = RateLimiter()
    metrics = Metrics()

    @app.middleware("http")
    async def harden(request: Request, call_next):
        started = time.perf_counter()
        request_id = request.headers.get("x-request-id", "")
        if not _REQUEST_ID.match(request_id):
            request_id = uuid4().hex

        def deny(status: int, detail: str, kind: str, extra: dict[str, str] | None = None):
            metrics.reject(kind)
            metrics.observe(status, time.perf_counter() - started)
            return JSONResponse(
                {"detail": detail},
                status_code=status,
                headers={
                    **security_headers(),
                    "X-Request-ID": request_id,
                    **(extra or {}),
                },
            )

        if request.method not in {"GET", "HEAD", "OPTIONS"} and not api_key.allows(
            request.headers.get("x-api-key")
        ):
            return deny(401, "invalid or missing API key", "auth")
        length = request.headers.get("content-length")
        if length:
            try:
                size = int(length)
            except ValueError:
                size = 0
            if size > max_body_bytes():
                return deny(413, "request body too large", "body_limit")
        client = request.client.host if request.client else "unknown"
        decision = limiter.check(client)
        if not decision.allowed:
            return deny(
                429,
                "rate limit exceeded",
                "rate_limit",
                {
                    "Retry-After": str(decision.retry_after),
                    "X-RateLimit-Limit": str(limiter.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )
        if request.url.path != "/immunity/reset":
            immune_verdict = immune.pre_check(client, request.url.path)
        else:
            immune_verdict = None
        if immune_verdict is not None and not immune_verdict.allowed:
            return deny(
                403,
                "client is temporarily quarantined by the immune system",
                "immune",
                {"Retry-After": str(immune_verdict.retry_after)},
            )
        try:
            response = await call_next(request)
        except Exception:
            metrics.observe(500, time.perf_counter() - started)
            raise
        metrics.observe(response.status_code, time.perf_counter() - started)
        immune_result = immune.observe(
            client,
            request.url.path,
            response.status_code,
            time.perf_counter() - started,
            request.method,
        )
        for name, value in security_headers().items():
            response.headers.setdefault(name, value)
        response.headers["X-RateLimit-Limit"] = str(limiter.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Immune-Score"] = str(immune_result["score"])
        return response

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "name": "sovereign-fabric",
            "note": "honest self-evolving fabric; no claim is reported without evidence",
            "dashboard": "/dashboard",
            "endpoints": [
                "GET /health",
                "GET /ready",
                "GET /metrics",
                "GET /diagnostics",
                "GET /dashboard",
                "GET /guardians",
                "POST /consult",
                "POST /absorb",
                "GET /knowledge/search",
                "GET /capabilities",
                "GET /capabilities/search",
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
                "GET /self",
                "GET /properties",
                "GET /security/audit",
                "GET /security/sbom",
                "GET /security/report",
                "POST /brief",
                "GET /mastery",
                "POST /mastery/practice",
                "POST /verify_claim",
                "POST /ask",
                "POST /invoke",
                "POST /invoke/batch",
                "POST /pipeline",
                "POST /feedback",
                "GET /feedback/summary",
                "POST /self/repair",
                "POST /expert/ask",
                "GET /immunity/status",
                "GET /immunity/incidents",
                "POST /immunity/scan",
                "POST /immunity/reset",
                "GET /collective/status",
                "GET /collective/export",
                "POST /collective/import",
                "GET /autonomy",
                "GET /evolution/reward",
                "GET /protocol",
                "POST /protocol/execute",
                "POST /protocol/language",
                "POST /optimize",
                "GET /loop/status",
                "POST /loop/start",
                "POST /loop/stop",
                "POST /loop/tick",
                "GET /report",
                "GET /report.md",
                "GET /cycles",
                "GET /failures",
                "POST /validate",
            ],
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

    @app.post("/invoke")
    def invoke(body: InvokeRequest) -> dict[str, Any]:
        try:
            result = engine.registry.invoke(body.capability, body.payload)
        except CapabilityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"capability": body.capability, "result": result}

    @app.post("/invoke/batch")
    def invoke_batch(body: BatchInvokeRequest) -> dict[str, Any]:
        started = time.perf_counter()
        results: list[dict[str, Any]] = []
        for call in body.calls:
            try:
                result = engine.registry.invoke(call.capability, call.payload)
                results.append(
                    {"ok": True, "capability": call.capability, "result": result}
                )
            except Exception as exc:
                results.append(
                    {
                        "ok": False,
                        "capability": call.capability,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        return {
            "ok": all(item["ok"] for item in results),
            "results": results,
            "elapsed_s": round(time.perf_counter() - started, 6),
        }

    @app.post("/expert/ask")
    def expert_ask(body: ExpertAskRequest) -> dict[str, Any]:
        if not engine.experts:
            raise HTTPException(
                status_code=503,
                detail="no external expert is configured; set GROQ_API_KEY or OPENAI_API_KEY",
            )
        failures: list[str] = []
        for expert in engine.experts:
            try:
                answer = expert.complete(body.system, body.question)
            except Exception as exc:
                failures.append(f"{expert.name}: {type(exc).__name__}")
                continue
            return {
                "ok": True,
                "expert": expert.name,
                "answer": str(answer)[:8000],
                "verified": False,
                "note": "unverified external model output; it is text, not an executed action",
            }
        raise HTTPException(
            status_code=502,
            detail={"message": "every configured expert failed", "failures": failures},
        )

    @app.post("/feedback")
    def feedback_endpoint(body: FeedbackRequest) -> dict[str, Any]:
        try:
            payload = record_feedback(
                store, body.capability, body.rating, body.note, body.request_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "feedback": payload}

    @app.get("/feedback/summary")
    def feedback_summary_endpoint() -> dict[str, Any]:
        return {"rows": feedback_summary(store)}

    @app.post("/self/repair")
    def self_repair_endpoint() -> dict[str, Any]:
        return repair(engine)

    @app.post("/pipeline")
    def pipeline(body: PipelineRequest) -> dict[str, Any]:
        try:
            return run_pipeline(engine.registry, [step.model_dump() for step in body.steps])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/capabilities/search")
    def capability_search(
        q: str = Query(min_length=1, max_length=200),
        k: int = Query(default=5, ge=1, le=50),
    ) -> dict[str, Any]:
        qvec = embed(q)
        scores = feedback_scores(store)
        hits = []
        for cap in engine.registry.list_active():
            text = " ".join(
                [cap.name, cap.description, *cap.inputs, *cap.outputs]
            )
            feedback = scores.get(cap.name, 0.0)
            hits.append(
                {
                    "name": cap.name,
                    "description": cap.description,
                    "inputs": list(cap.inputs),
                    "outputs": list(cap.outputs),
                    "score": round(cosine(qvec, embed(text)) + 0.05 * feedback, 6),
                    "feedback": feedback,
                }
            )
        hits.sort(key=lambda item: (-item["score"], item["name"]))
        return {"query": q, "hits": hits[:k]}

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

    @app.get("/capabilities/{name}")
    def capability_detail(name: str) -> dict[str, Any]:
        versions = [cap for cap in store.list_capabilities() if cap.name == name]
        if not versions:
            raise HTTPException(status_code=404, detail=f"unknown capability {name!r}")
        active = engine.registry.active(name)
        return {
            "name": name,
            "active": None if active is None else active.version,
            "versions": [
                {
                    "version": cap.version,
                    "status": cap.status,
                    "kind": cap.kind,
                    "inputs": list(cap.inputs),
                    "outputs": list(cap.outputs),
                    "description": cap.description,
                }
                for cap in versions
            ],
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

    @app.get("/ready")
    def ready() -> JSONResponse:
        checks: dict[str, Any] = {}
        try:
            checks["database"] = engine.store.count_knowledge() >= 0
        except Exception:
            checks["database"] = False
        active = engine.registry.list_active()
        checks["capabilities"] = bool(active)
        checks["guardians"] = bool(engine.guardians.names())
        checks["planner"] = engine.pathfinder.plan(
            ("text",), "markdown", operators_from(active)
        ).solved
        ok = all(checks.values())
        return JSONResponse(
            {"ok": ok, "checks": checks}, status_code=200 if ok else 503
        )

    @app.get("/immunity/status")
    def immunity_status() -> dict[str, Any]:
        return immune.status()

    @app.get("/immunity/incidents")
    def immunity_incidents(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
        return {"incidents": immune.incidents(limit), "status": immune.status()}

    @app.post("/immunity/scan")
    def immunity_scan() -> dict[str, Any]:
        return immune.scan()

    @app.post("/immunity/reset")
    def immunity_reset(clear_history: bool = True) -> dict[str, Any]:
        return immune.reset(clear_history=clear_history)

    @app.get("/collective/status")
    def collective_status_endpoint() -> dict[str, Any]:
        return collective_status(store)

    @app.get("/collective/export")
    def collective_export(limit: int = Query(default=200, ge=1, le=500)) -> dict[str, Any]:
        return export_bundle(store, limit=limit)

    @app.post("/collective/import")
    def collective_import(bundle: dict[str, Any]) -> dict[str, Any]:
        return import_bundle(store, bundle)

    @app.get("/autonomy")
    def autonomy_endpoint() -> dict[str, Any]:
        return assess(
            engine,
            loop_status=loop.status(),
            immune_status=immune.status(),
            collective=collective_status(store),
        )

    @app.get("/evolution/reward")
    def evolution_reward() -> dict[str, Any]:
        return reward_ledger(store)

    @app.get("/protocol")
    def protocol_status() -> dict[str, Any]:
        return {
            "protocol": "sovereign-deterministic/v1",
            "routes": [
                route.__dict__
                for route in protocol.routes("markdown", ("text",), None)
            ],
            "banned_phrases": len(BANNED_PHRASES),
            "freshness_window_days": 180,
            "language_policy": (
                "report a verified result and its mechanism, or report the exact "
                "gap and the next executable action"
            ),
            "verified_definition": (
                "all six validator criteria pass and execution succeeds"
            ),
            "limits": [
                "verified is not a semantic proof of intent",
                "the route search is bounded",
                "open-ended goals still require relevant sources or a synthesis specification",
            ],
        }

    @app.post("/protocol/execute")
    def protocol_execute(body: ProtocolRequest) -> dict[str, Any]:
        return protocol.execute(
            body.request,
            goal_type=body.goal_type,
            initial=tuple(body.initial) if body.initial else None,
            text=body.text,
            sources=body.sources,
            synthesize=body.synthesize,
            budget_s=body.budget_s,
            max_alternatives=body.max_alternatives,
        )

    @app.post("/protocol/language")
    def protocol_language(body: LanguageRequest) -> dict[str, Any]:
        return {
            "compliant": audit_language(body.text).compliant,
            "violations": audit_language(body.text).violations,
            "policy": audit_language(body.text).policy,
        }

    @app.get("/metrics")
    def metrics_endpoint() -> PlainTextResponse:
        immune_status = immune.status()
        return PlainTextResponse(
            metrics.render(
                {
                    "capabilities": len(engine.registry.list_active()),
                    "knowledge_units": engine.store.count_knowledge(),
                    "cycles": len(store.list_events("cycle")),
                    "optimizations": len(store.list_events("capability.optimized")),
                    "feedback": len(store.list_events("feedback", 5000)),
                    "immune_observations": immune_status["observations"],
                    "immune_quarantines": immune_status["quarantines_total"],
                    "collective_lessons": collective_status(store)["lessons"],
                }
            )
        )

    @app.get("/diagnostics")
    def diagnostics_endpoint() -> dict[str, Any]:
        report = diagnose(engine)
        return report

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "ok": True,
            "version": "0.1.0",
            "capabilities": len(engine.registry.list_active()),
            "knowledge_units": store.count_knowledge(),
            "api_key_required": api_key.enabled,
            "rate_limit_per_window": limiter.limit,
            "immune_quarantined": immune.status()["quarantined"],
            "collective_lessons": collective_status(store)["lessons"],
        }

    @app.get("/security/audit")
    def security_audit_endpoint(online: bool = True) -> dict[str, Any]:
        return security_audit(online=online)

    @app.get("/security/sbom")
    def security_sbom_endpoint() -> dict[str, Any]:
        return cyclonedx_sbom(security_audit(online=False))

    @app.get("/security/report")
    def security_report_endpoint(online: bool = True) -> PlainTextResponse:
        return PlainTextResponse(
            disclosure_markdown(security_audit(online=online)),
            media_type="text/markdown",
        )

    @app.post("/brief")
    def brief(body: BriefRequest) -> dict[str, Any]:
        return build_brief(
            engine,
            body.query,
            limit=body.limit,
            sources=body.sources,
            lang=body.lang,
            deadline_s=body.deadline_s,
        )

    @app.get("/mastery")
    def mastery() -> dict[str, Any]:
        model = Mastery(engine)
        return {"table": model.table(), "weakest": model.weakest()}

    @app.post("/mastery/practice")
    def mastery_practice(iterations: int = 1, budget_s: float = 8.0) -> dict[str, Any]:
        return Mastery(engine).practice(iterations=iterations, budget_s=budget_s)

    @app.post("/verify_claim")
    def verify(body: ClaimRequest) -> dict[str, Any]:
        return verify_claim(store, body.claim, k=body.k)

    @app.get("/properties")
    def properties(cases: int = 30) -> dict[str, Any]:
        return check_capabilities(engine.registry, cases=cases)

    @app.get("/self")
    def self_model() -> dict[str, Any]:
        return SelfModel(engine).assess()

    @app.post("/ask")
    def ask(body: AskRequest) -> dict[str, Any]:
        intent = parse_intent(body.request)
        cycle = engine.evolve(
            intent["request"],
            goal_type=intent["goal_type"],
            initial=(intent.get("initial") or "text",),
            text=intent["text"],
            sources=body.sources,
            budget_s=body.budget_s,
            auto_extend=body.auto_extend,
            max_attempts=2,
        )
        return {
            "intent": intent,
            "ok": cycle.ok,
            "plan": [step.capability for step in cycle.plan.steps],
            "result": cycle.execution.get("value"),
            "validation": {
                "passed": cycle.validation.passed,
                "scores": cycle.validation.scores,
                "failures": cycle.validation.failures,
            },
            "diagnosis": cycle.diagnosis,
            "duration_s": round(cycle.duration_s, 4),
        }

    @app.post("/optimize")
    def optimize(name: str | None = None, repeats: int = 10) -> dict[str, Any]:
        if name:
            return optimizer.optimize(name, repeats=repeats)
        return {"results": optimizer.optimize_all(repeats=repeats)}

    @app.post("/loop/start")
    def loop_start() -> dict[str, Any]:
        return loop.start()

    @app.post("/loop/stop")
    def loop_stop() -> dict[str, Any]:
        return loop.stop()

    @app.get("/loop/status")
    def loop_status() -> dict[str, Any]:
        return loop.status()

    @app.post("/loop/tick")
    def loop_tick() -> dict[str, Any]:
        return loop.tick()

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
