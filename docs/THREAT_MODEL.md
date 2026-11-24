# Threat Model

## Assets

- Source integrity and the audit trail.
- User input and any data derived from it.
- API availability and the host running it.
- Secrets in the environment.
- The dependency supply chain.
- The honesty of the disclosure report.

## Trust boundaries

1. **User to API**: untrusted input crosses into Pydantic models and guards.
2. **API to guardians**: external text is untrusted; it is parsed, not
   executed.
3. **API to synthesized code**: generated Python runs in a separate process
   with a sanitized environment and a timeout.
4. **API to OSV**: the response is advisory data, not executable.
5. **Repository to CI**: a pull request is untrusted until tests and the strict
   audit pass.

## STRIDE

| Threat | Example | Mitigation | Residual risk |
| --- | --- | --- | --- |
| Spoofing | Forged API client | Optional `X-API-Key`, constant-time compare | GET endpoints are public by design |
| Tampering | Modified dependency or source, spam feedback | Hash manifest, licence audit, CI, review, rate-limited feedback, event log | Feedback is unauthenticated by default and can reorder search; no signed commits enforced |
| Repudiation | Unlogged mutation | Append-only event log for cycles and optimizations | API access logs are not persisted |
| Information disclosure | Question sent to an external model | Only the user question and optional system text are sent; no environment, store, or knowledge units; response marked unverified | The provider's retention policy is outside this system |
| Information disclosure | Secret in source or response | Secret pattern scan, sanitized subprocess env, no secrets in reports; `/metrics` and `/diagnostics` report counts and static findings, never environment values | A new secret format can evade the regex |
| Denial of service | Huge body, request flood, huge guardian response, long pipeline, feedback flood | 2 MB API body cap, per-client sliding window, 2 MB guardian fetch cap, 20-step pipeline cap, 20-call batch cap, per-capability input caps, rating validation | Limiter is in-process; the feedback table has no retention policy |
| Elevation of privilege | `eval`/`exec` escape, repair abuse | AST evaluator, isolated subprocess, no shell; pipeline can only call registered capabilities; repair only quarantines broken built-ins and restores known names | Subprocess is not a full OS sandbox |
| Prompt injection | Malicious guardian or expert text | Text is data; expert answers are marked unverified and never executed | A future LLM tool-use path could be influenced |

## Out of scope

- Attacks on third-party guardians or model providers.
- Physical access to the host.
- Supply-chain attacks that also compromise the CI runner.
- A formal proof of correctness or of the absence of vulnerabilities.

## Review triggers

Re-run the threat model when adding a guardian, a network call, a new input
field, a new subprocess, an authentication path, or a dependency.
