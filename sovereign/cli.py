"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from .capabilities import bootstrap_native, CapabilityRegistry
from .evolution import EvolutionEngine
from .store import FabricStore

_DEMO_EXAMPLES: dict[str, list[Any]] = {
    "upper": [({"value": "abc"}, {"value": "ABC"}), ({"value": "x1"}, {"value": "X1"})],
    "lower": [({"value": "ABC"}, {"value": "abc"})],
    "reverse": [({"value": "abc"}, {"value": "cba"})],
    "length": [({"value": "abcd"}, {"value": 4})],
    "sum_list": [({"value": [1, 2, 3]}, {"value": 6})],
    "identity": [({"value": "same"}, {"value": "same"})],
}


def _build_engine(db: str) -> EvolutionEngine:
    return EvolutionEngine(FabricStore(db))


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sovereign")
    parser.add_argument("--db", default=os.environ.get("SOVEREIGN_DB", "sovereign.db"))
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the HTTP service")
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "12000")))
    serve.add_argument("--host", default="0.0.0.0")

    consult = sub.add_parser("consult", help="consult external guardians")
    consult.add_argument("query")
    consult.add_argument("--limit", type=int, default=5)

    search = sub.add_parser("search", help="search absorbed knowledge")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=5)

    sub.add_parser("capabilities", help="list capabilities")

    evolve = sub.add_parser("evolve", help="run one evolution cycle")
    evolve.add_argument("request")
    evolve.add_argument("--goal-type", default="markdown")
    evolve.add_argument("--text", default=None)
    evolve.add_argument("--budget", type=float, default=5.0)
    evolve.add_argument(
        "--op",
        default=None,
        help="synthesize a capability with this template op before replanning",
    )
    evolve.add_argument("--capability-name", default="text.upper")
    evolve.add_argument("--auto-extend", action="store_true")
    evolve.add_argument("--attempts", type=int, default=1)

    curriculum = sub.add_parser("curriculum", help="run self-directed practice tasks")
    curriculum.add_argument("--iterations", type=int, default=3)
    curriculum.add_argument("--budget", type=float, default=10.0)
    curriculum.add_argument("--sources", nargs="*", default=None)
    curriculum.add_argument("--no-auto-extend", action="store_true")

    sub.add_parser("redteam", help="audit the overclaim guardrail")

    bench = sub.add_parser("bench", help="measure batch execution throughput")
    bench.add_argument("--n", type=int, default=100000)
    bench.add_argument("--capability", default="text.tokenize")
    bench.add_argument(
        "--mode", default="processes", choices=["auto", "serial", "threads", "processes"]
    )
    bench.add_argument("--workers", type=int, default=None)
    bench.add_argument("--workload", default="tokenize", choices=["tokenize", "cpu"])
    bench.add_argument("--iterations", type=int, default=20000)

    report = sub.add_parser("report", help="run the full loop and print a judged report")
    report.add_argument("--query", default="retrieval augmented generation")
    report.add_argument("--goal-type", default="markdown")
    report.add_argument("--budget", type=float, default=15.0)
    report.add_argument("--benchmark-n", type=int, default=500)
    report.add_argument("--sources", nargs="*", default=None)
    report.add_argument("--markdown", action="store_true")

    optimize = sub.add_parser("optimize", help="benchmark equivalent implementations and keep the faster")
    optimize.add_argument("--name", default=None)
    optimize.add_argument("--all", action="store_true")
    optimize.add_argument("--repeats", type=int, default=10)

    loop = sub.add_parser("loop", help="run bounded continuous-evolution ticks")
    loop.add_argument("--interval", type=float, default=30.0)
    loop.add_argument("--ticks", type=int, default=0)
    loop.add_argument("--sources", nargs="*", default=None)

    brief = sub.add_parser("brief", help="cited extractive brief for any topic")
    brief.add_argument("query")
    brief.add_argument("--limit", type=int, default=5)
    brief.add_argument("--lang", choices=["en", "ar"], default="en")
    brief.add_argument("--sources", nargs="*", default=None)

    mastery = sub.add_parser("mastery", help="mastery table and weakest-goal practice")
    mastery.add_argument("--practice", type=int, default=0)
    mastery.add_argument("--budget-s", type=float, default=8.0)
    mastery.add_argument("--sources", nargs="*", default=None)

    self_parser = sub.add_parser("self", help="precise self-assessment from evidence")
    properties = sub.add_parser("properties", help="run property checks over native capabilities")
    properties.add_argument("--cases", type=int, default=30)
    verify = sub.add_parser("verify", help="check lexical support for a claim")
    verify.add_argument("claim")

    ask = sub.add_parser("ask", help="route an Arabic or English request into a full cycle")
    ask.add_argument("request")
    ask.add_argument("--budget", type=float, default=10.0)
    ask.add_argument("--sources", nargs="*", default=None)

    args = parser.parse_args(argv)

    if args.command == "serve":
        import uvicorn

        from .api import create_app

        uvicorn.run(create_app(args.db), host=args.host, port=args.port)
        return 0

    engine = _build_engine(args.db)

    if args.command == "consult":
        result = engine.guardians.consult(args.query, args.limit)
        _print(
            {
                "sources": result.sources,
                "units": [
                    {"title": u.title, "source": u.provenance.source, "url": u.provenance.url}
                    for u in result.units
                ],
            }
        )
    elif args.command == "search":
        hits = engine.store.search_knowledge(args.query, args.k)
        _print([{"score": round(s, 4), "title": u.title, "source": u.provenance.source} for u, s in hits])
    elif args.command == "capabilities":
        _print(
            [
                {"name": c.name, "version": c.version, "kind": c.kind, "status": c.status}
                for c in engine.store.list_capabilities()
            ]
        )
    elif args.command == "evolve":
        synthesize = None
        if args.op:
            if args.op not in _DEMO_EXAMPLES:
                parser.error(f"unknown op {args.op!r}; choose from {sorted(_DEMO_EXAMPLES)}")
            synthesize = {
                "name": args.capability_name,
                "description": f"{args.op} transform",
                "inputs": ("text",),
                "outputs": (args.op,),
                "spec": {"op": args.op},
                "examples": _DEMO_EXAMPLES[args.op],
            }
        goal_type = args.op if args.op else args.goal_type
        cycle = engine.evolve(
            args.request,
            goal_type=goal_type,
            text=args.text,
            synthesize=synthesize,
            budget_s=args.budget,
            auto_extend=args.auto_extend,
            max_attempts=args.attempts,
        )
        _print(
            {
                "ok": cycle.ok,
                "plan": [s.capability for s in cycle.plan.steps],
                "execution_ok": cycle.execution.get("ok"),
                "result": cycle.execution.get("value"),
                "sources": cycle.consultation.sources,
                "extensions": cycle.extensions,
                "diagnosis": cycle.diagnosis,
                "validation": {
                    "passed": cycle.validation.passed,
                    "scores": {k: round(v, 2) for k, v in cycle.validation.scores.items()},
                    "failures": cycle.validation.failures,
                    "overclaims": cycle.validation.overclaims,
                },
                "duration_s": round(cycle.duration_s, 4),
            }
        )
    elif args.command == "curriculum":
        from .curriculum import Curriculum

        results = Curriculum(engine).run(
            iterations=args.iterations,
            sources=args.sources,
            budget_s=args.budget,
            auto_extend=not args.no_auto_extend,
        )
        _print({"results": results})
    elif args.command == "redteam":
        from .redteam import audit

        _print(audit(engine.validator))
    elif args.command == "bench":
        from .execution import benchmark

        _print(
            benchmark(
                args.n,
                args.capability,
                args.mode,
                args.workers,
                workload=args.workload,
                iterations=args.iterations,
            )
        )
    elif args.command == "brief":
        from .brief import build_brief

        _print(
            build_brief(
                engine,
                args.query,
                limit=args.limit,
                sources=args.sources,
                lang=args.lang,
            )
        )
    elif args.command == "mastery":
        from .mastery import Mastery

        model = Mastery(engine)
        if args.practice:
            _print(
                model.practice(
                    iterations=args.practice,
                    budget_s=args.budget_s,
                    sources=args.sources,
                )
            )
        else:
            _print({"table": model.table(), "weakest": model.weakest()})
    elif args.command == "self":
        from .selfmodel import SelfModel

        _print(SelfModel(engine).assess())
    elif args.command == "properties":
        from .properties import check_capabilities

        _print(check_capabilities(engine.registry, cases=args.cases))
    elif args.command == "verify":
        from .evidence import verify_claim

        _print(verify_claim(engine.store, args.claim))
    elif args.command == "ask":
        from .intent import parse_intent

        intent = parse_intent(args.request)
        cycle = engine.evolve(
            intent["request"],
            goal_type=intent["goal_type"],
            text=intent["text"],
            sources=args.sources,
            budget_s=args.budget,
            auto_extend=True,
            max_attempts=2,
        )
        _print(
            {
                "intent": intent,
                "ok": cycle.ok,
                "plan": [step.capability for step in cycle.plan.steps],
                "validation": {
                    "passed": cycle.validation.passed,
                    "scores": cycle.validation.scores,
                    "failures": cycle.validation.failures,
                },
                "diagnosis": cycle.diagnosis,
            }
        )
    elif args.command == "optimize":
        from .optimizer import Optimizer

        optimizer = Optimizer(engine.registry)
        result = (
            optimizer.optimize(args.name, repeats=args.repeats)
            if args.name
            else optimizer.optimize_all(repeats=args.repeats)
        )
        _print(result)
    elif args.command == "loop":
        from .loop import EvolutionLoop

        evolution_loop = EvolutionLoop(
            engine, interval_s=args.interval, sources=args.sources
        )
        if args.ticks:
            for _ in range(args.ticks):
                _print(evolution_loop.tick())
        else:
            evolution_loop.start()
            print("loop running; press Ctrl+C to stop")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                _print(evolution_loop.stop())
    elif args.command == "report":
        from .report import render_report, system_report

        report = system_report(
            engine,
            query=args.query,
            goal_type=args.goal_type,
            sources=args.sources,
            budget_s=args.budget,
            benchmark_n=args.benchmark_n,
        )
        print(render_report(report) if args.markdown else json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
