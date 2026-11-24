"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
