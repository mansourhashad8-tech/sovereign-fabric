# Contributing

## Before you start

- Read `SECURITY.md` and `OPENNESS.md`.
- Report vulnerabilities privately through Security Advisories, never in a
  public issue.
- Keep changes small enough to review in one sitting.

## Local checks

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m sovereign audit --strict
```

A pull request is ready when:

- the tests pass,
- the strict audit passes with no high/critical finding and no unknown
  licence,
- no secret, database, or personal data is included,
- the change is described with what changed and why,
- new behaviour has a test that exercises the real code path.

## Style

- Prefer the standard library.
- Keep comments for non-obvious invariants, not for narrating the diff.
- Do not add a dependency unless it is open source and the audit can classify
  its licence.
- Do not weaken a guard or a validator to make a test pass.

## Review

Reviewers check correctness, security, and whether the claim matches the
evidence. A confident claim without a measurement is a defect.
