# Sovereign Fabric

A self-evolving cognitive-executive system built around one rule: **it may
retry anything, but it may not claim anything it cannot show.**

It consults external sources, absorbs what it learns into a single fabric of
knowledge and executable capabilities, plans with classical search, extends
itself only through a verification gate, and runs every result through a
holistic validator that refuses overclaims.

This README is deliberately blunt about limits. A system that exaggerates its
own powers is not sovereign; it is a liability.

---

## What this is

- **An external-guardianship layer** over real public sources: arXiv, OpenAlex,
  Semantic Scholar, Crossref, GitHub, Hacker News, Hugging Face, PyPI, npm,
  plus an offline engineering corpus. Each result carries provenance (source,
  URL, retrieval time, licence, confidence).
- **A unified fabric**: one SQLite store holds knowledge units, a concept
  graph, the capability registry, an append-only event log, a source cache and
  a failure memo. Knowledge retrieval and execution planning read the same
  store.
- **Instant absorption**: consulting, indexing (deterministic embeddings) and
  graph-linking happen in one pass, so a consulted fact is immediately
  searchable and traversable.
- **A capability registry** with versioning, hot-swap, quarantine and rollback.
- **Autonomous acquisition**: when planning is blocked, the system looks for a
  blueprint whose inputs are already reachable and whose outputs add something
  new, synthesises it through the gate, and re-plans. It can chain several such
  acquisitions to build a multi-step bridge.
- **A bounded repair loop**: a cycle that fails a criterion retries with a
  broader query, keeps the best attempt, records every attempt, and returns an
  actionable diagnosis.
- **Self-extension through a gate**: the system generates a capability from a
  behavioural spec and admits it only if it reproduces every example inside a
  separate interpreter with a timeout and a sanitized environment. Failures are
  quarantined, never silently kept.
- **Classical best-first planning** over capability types, with parallel
  multi-goal search and a failure memo that prunes proven dead ends — keyed to
  the operator set, so registering a new capability correctly re-opens search.
- **A holistic validator** scoring six criteria and rejecting absolute or
  unfalsifiable language (negation-aware).

## What this is not

| Claim | Reality |
| --- | --- |
| "A living entity" | It is software. No consciousness, no autonomy beyond its loop. |
| "A million times faster" | No such speedup exists here. Speed is *measured* against a budget; unmeasured speed scores zero. |
| "Quantum pathfinding" | The planner is classical A*. A quantum *simulator* gives no speedup over the algorithm it simulates; only real quantum hardware might, and none is used. |
| "Never fails" | It retries, degrades gracefully and reports honestly. If it cannot meet a criterion, it says so and returns `ok: false`. |
| "General program synthesis" | Template synthesis over a small operation set. The *gate* is general; the generator is not. |

## The six pillars, mapped

| Pillar | Implementation | Honest limit |
| --- | --- | --- |
| 1. External guardianship | `sovereign/guardians/` — protocol, parallel registry, cache, rate limits, per-source status | A dead source degrades the result; it does not fail the run |
| 2. Unified cognitive/executive fabric | `store.py` — knowledge, graph, capabilities, events in one DB | Lexical hashed embeddings, not a semantic model |
| 3. Accelerated self-engineering | `synthesis.py` + `capabilities.py` — generate, verify, admit, roll back | Narrow template generator; hard verification gate |
| 4. Constraint transcendence | `pathfinder.py` — retry alternate routes, reframe goals, prune dead ends | Constraints are engineering problems, not magic |
| 5. Hyper-accelerated determinism | deterministic embeddings, deterministic search, memoised failures, retry loop | "Hyper" is aspiration, not a measured property |
| 6. Holistic validation | `validator.py` — six scores + overclaim refusal | The validator can be wrong; it is auditable and tested |

## Architecture

```
sovereign/
  models.py        value objects (Provenance, KnowledgeUnit, Capability, Evidence, Plan)
  vectors.py       deterministic signed-hash embeddings
  store.py         unified SQLite fabric (knowledge, graph, capabilities, events, cache, memo)
  guardians/
    base.py        Guardian protocol, parallel registry, cache, rate limiter
    sources.py     arXiv, OpenAlex, Semantic Scholar, Crossref, GitHub, Hacker
                   News, Hugging Face, PyPI, npm, local corpus
  absorption.py    consult -> index -> link, in one pass
  capabilities.py  versioned registry, hot-swap, rollback, sandboxed invocation
  native.py        built-in transform chain
  blueprints.py    behavioural specs + autonomous acquisition when planning is blocked
  synthesis.py     spec -> generate -> verify in subprocess -> admit/quarantine
  pathfinder.py    A* over capability types, parallel multi-goal, failure memo
  validator.py     six-criterion scoring + overclaim refusal
  evolution.py     one cycle: consult -> absorb -> plan -> acquire? -> execute
                   -> validate; plus a bounded repair loop and diagnosis
  api.py           FastAPI service
  cli.py           command-line interface
```

## Quickstart

```bash
pip install fastapi uvicorn httpx pytest

# service on :12000
python -m sovereign.cli serve --port 12000

# consult real sources
curl -s -X POST localhost:12000/consult -H 'Content-Type: application/json' \
  -d '{"query":"retrieval augmented generation","limit":3}'

# run a full cycle against real guardians
curl -s -X POST localhost:12000/evolve -H 'Content-Type: application/json' \
  -d '{"request":"retrieval augmented generation","text":"rag improves grounding","goal_type":"markdown","budget_s":10}'

# self-extend: synthesize a missing capability, then replan and execute
curl -s -X POST localhost:12000/evolve -H 'Content-Type: application/json' \
  -d '{"request":"retrieval augmented generation","goal_type":"upper","initial":["text"],"text":"hello world","synthesize":{"name":"text.upper","description":"uppercase","inputs":["text"],"outputs":["upper"],"spec":{"op":"upper"},"examples":[[{"value":"abc"},{"value":"ABC"}]]}}'

# autonomous: supply no spec; the entity finds and verifies its own capability
curl -s -X POST localhost:12000/evolve -H 'Content-Type: application/json' \
  -d '{"request":"retrieval augmented generation","goal_type":"doubled","initial":["text"],"text":"ab","auto_extend":true,"max_attempts":2}'
```

Offline (no network) it still works, but the validator correctly reports
`guardianship = 0` and returns `ok: false` — doing the work is not the same as
meeting every criterion.

## Honesty model

1. **Provenance or it did not happen.** Every knowledge unit and capability
   carries its source.
2. **Evidence or it is a hypothesis.** `validate` fails a claim set with no
   evidence.
3. **Measured speed only.** Speed is `budget / measured_duration`; a missing
   measurement scores 0.
4. **Overclaims are refused.** "Million-fold", "quantum advantage",
   "guaranteed", "no failures", "impossible", "living entity", "AGI" fail the
   gate — unless negated ("we do not claim quantum advantage").
5. **Generated code is quarantined until it passes.** Verification runs in a
   subprocess with a timeout and a secret-stripped environment.
6. **Failures are remembered.** Proven dead ends are pruned on later runs,
   scoped to the operator set that produced them.

## Tests

```bash
python -m pytest        # 76 tests
```

Coverage includes: embedding determinism, hybrid retrieval and graph traversal,
store/graph/versioning, all ten guardian parsers against recorded fixtures,
cache and graceful degradation, absorption and graph linking, built-in and
sandboxed invocation, secret stripping, the synthesis gate
(accept/reject/quarantine), A* correctness and memoisation (including the
world-signature fix), autonomous blueprint acquisition (single-step,
multi-step bridge, unmet inputs, quarantine), validator scoring and
negation-aware overclaim detection, the full evolution cycle (success,
local-only refusal, overclaim refusal, synthesis path, autonomous extension,
multi-attempt repair, failure memo), and the HTTP API.
