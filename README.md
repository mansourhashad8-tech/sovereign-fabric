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
- **Recruited experts**: any OpenAI-compatible model can be asked for candidate
  implementations; every candidate still has to pass the local gate.
- **Self-directed practice**: the system forms small tasks from its own absorbed
  knowledge and attempts them, recording what worked.
- **A guardrail that attacks itself**: a red-team corpus measures the overclaim
  detector's blind spots, and the patterns are widened from what it finds.
- **Self-extension through a gate**: the system generates a capability from a
  behavioural spec and admits it only if it reproduces every example inside a
  separate interpreter with a timeout and a sanitized environment. Failures are
  quarantined, never silently kept.
- **Classical best-first planning** over capability types, with parallel
  multi-goal search and a failure memo that prunes proven dead ends — keyed to
  the operator set, so registering a new capability correctly re-opens search.
- **A holistic validator** scoring six criteria and rejecting absolute or
  unfalsifiable language (negation-aware).

## Recruiting other minds (external experts)

The system does not have to be the only model in the loop. `sovereign/expert.py`
speaks the OpenAI chat-completions protocol, so Groq, OpenAI, or a local server
can act as an expert. `sovereign/acquire.py` asks every configured expert for
candidate implementations, verifies each against the examples, and — if all
fail — feeds the failures back and asks again.

Nothing an expert says is trusted. Its output is a *candidate*; the same
subprocess gate that checks generated code checks it. If no expert is
reachable, acquisition says so and returns no capability.

```bash
export GROQ_API_KEY=...        # and/or OPENAI_API_KEY / OPENAI_BASE_URL
```

In this workspace the Groq key is present but the provider returns `401`, so
the live attempt records the error and admits nothing. The pipeline is
exercised end-to-end with injected experts in the tests.

## Self-directed practice

`POST /curriculum` picks concepts the system has absorbed, forms small tasks,
and attempts them with its planner, gate, and validator. This is a bounded
practice loop — the closest honest analogue to continuous self-evolution. It is
not curiosity.

## Attacking its own guardrail

`GET /redteam` pushes a corpus of absolute claims through the overclaim
detector and reports coverage. Red-teaming found a real bug: the `100%` pattern
had a trailing word-boundary that made it miss. Coverage is now 20/20 on the
corpus; that is evidence about the corpus, not proof of completeness.

## Many routes

When the first plan's execution fails, the engine asks the planner for
alternative routes (found by banning the last step of the previous plan) and
tries them before reporting failure.

## Execution: parallel, cached, speculative, remote-optional

`sovereign/execution.py` is a real batch engine, not a metaphor.

- **Parallelism**: serial, threads, and processes. `auto` uses processes for
  batches of 64 or more. The engine runs the same workload serially first and
  reports the measured ratio. On this 4-core box, 2000 CPU-heavy tasks took
  3.0s serially and 1.25s across four processes: **2.36x**. The same tokenize
  batch is *slower* in parallel (0.44x) because pickling costs more than the
  work, and the engine says so instead of hiding it.
- **Hot cache**: content-addressed in-process cache with TTL. Search results and
  embeddings are cached; measured hit latency is about **4 microseconds**. This
  is the only place where "sub-millisecond" is true.
- **Speculative prefetch**: when a request arrives, the engine predicts likely
  goals and warms embeddings for the request and its variants. A prediction is
  used only on an exact key match; otherwise it is discarded. `/evolve` warms,
  `/knowledge/search` verifies (see `prefetch_hit`).
- **Remote compute hook**: `RemoteExecutor` posts batches to
  `SOVEREIGN_REMOTE_EXECUTOR` when configured. With no endpoint it raises
  `RemoteUnavailable`, and `/remote/status` reports `available: false`. No HPC
  credentials exist here, so none is claimed.

```bash
python -m sovereign.cli bench --n 2000 --workload cpu --mode processes
```

## One command, one verdict

`GET /report` runs the whole loop and judges it: consult, absorb, plan, execute,
validate, benchmark, red-team, then pass its own prose through the overclaim
detector. `GET /report.md` renders the same report, and
`python -m sovereign.cli report --markdown` runs it locally.

Live run on 2026-11-24:

- 8/10 sources answered (arXiv and Semantic Scholar returned 429).
- First consultation 0.51s; second 0.045s (store cache plus failure cooldown).
- Plan: tokenize -> count -> summarize -> format; all six criteria passed.
- Measured 2.47x on 4 workers for a CPU-heavy batch.
- Red-team 20/20; the report's own prose contained no overclaim.

A source that fails is put in a 30-second cooldown instead of being retried on
every call, and a global deadline marks stragglers as `timeout` so one slow
source cannot hold the whole consultation.

## What this is not

| Claim | Reality |
| --- | --- |
| "A living entity" | It is software. No consciousness, no autonomy beyond its loop. |
| "A million times faster" | No such speedup exists here. Speed is *measured* against a budget; unmeasured speed scores zero. |
| "Quantum pathfinding" | The planner is classical A*. A quantum *simulator* gives no speedup over the algorithm it simulates; only real quantum hardware might, and none is used. |
| "Never fails" | It retries, degrades gracefully and reports honestly. If it cannot meet a criterion, it says so and returns `ok: false`. |
| "General program synthesis" | Template synthesis over a small operation set. The *gate* is general; the generator is not. |
| "Sub-millisecond execution for any task" | Only cache hits are microseconds; real work takes real time. |
| "Quantum parallel processing" | A classical process pool on 4 cores; measured 2.36x on CPU-heavy work and slower on trivial work. |
| "Borrowed supercomputers" | A remote hook exists; no endpoint is configured, so it refuses. |

## The six pillars, mapped

| Pillar | Implementation | Honest limit |
| --- | --- | --- |
| 1. External guardianship | `sovereign/guardians/` — protocol, parallel registry, cache, rate limits, per-source status | A dead source degrades the result; it does not fail the run |
| 2. Unified cognitive/executive fabric | `store.py` — knowledge, graph, capabilities, events in one DB | Lexical hashed embeddings, not a semantic model |
| 3. Accelerated self-engineering | `synthesis.py` + `capabilities.py` — generate, verify, admit, roll back | Narrow template generator; hard verification gate |
| 4. Constraint transcendence | `pathfinder.py` — retry alternate routes, reframe goals, prune dead ends | Constraints are engineering problems, not magic |
| 5. Hyper-accelerated determinism | deterministic embeddings, deterministic search, memoised failures, retry loop, measured batch speedup | 2.36x on 4 cores for CPU-heavy work; no universal acceleration |
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

# self-directed practice over its own absorbed knowledge
curl -s -X POST localhost:12000/curriculum -H 'Content-Type: application/json' \
  -d '{"iterations":2,"budget_s":25}'

# audit the overclaim guardrail
curl -s localhost:12000/redteam
```

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | status and source list |
| POST | `/consult` | query guardians, return provenance |
| POST | `/absorb` | consult and index into the fabric |
| GET | `/knowledge/search` | hybrid retrieval |
| GET | `/knowledge/graph` | traverse the concept graph |
| POST | `/synthesize` | spec -> verified capability |
| POST | `/acquire` | ask external experts for a verified capability |
| GET | `/experts` | configured experts |
| POST | `/validate` | six-criterion validation |
| POST | `/evolve` | full cycle (`auto_extend`, `max_attempts`) |
| POST | `/curriculum` | self-directed practice |
| GET | `/redteam` | guardrail coverage |
| POST | `/execute/batch` | parallel batch execution (measured) |
| GET | `/execute/benchmark` | serial vs parallel benchmark |
| GET | `/cache/stats` | cache and prefetch statistics |
| POST | `/cache/warm` | speculative embedding warm-up |
| GET | `/remote/status` | whether a remote executor is configured |
| GET | `/report` | full loop, measured, judged, self-audited |
| GET | `/report.md` | the same report as Markdown |
| GET | `/capabilities`, POST `/capabilities/rollback` | registry |
| GET | `/cycles`, `/failures` | audit log and failure memo |

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
python -m pytest        # 118 tests
```

Coverage includes: embedding determinism, hybrid retrieval and graph traversal,
store/graph/versioning, all ten guardian parsers against recorded fixtures,
cache and graceful degradation, absorption and graph linking, built-in and
sandboxed invocation, secret stripping, the synthesis gate
(accept/reject/quarantine), A* correctness, memoisation and alternative routes,
autonomous blueprint acquisition (single-step, multi-step bridge, unmet inputs,
quarantine), external-expert acquisition (accept, reject, iterative repair,
no-expert honesty), self-directed curriculum, red-team guardrail coverage,
batch execution across serial/threads/processes, measured-speedup honesty,
hot-cache hits and expiry, verified prefetch, remote-executor refusal,
consultation deadline and failure cooldown, the judged end-to-end report,
validator scoring and negation-aware overclaim detection, the full evolution
cycle (success, local-only refusal, overclaim refusal, synthesis path,
autonomous extension, multi-attempt repair, failure memo), and the HTTP API.
