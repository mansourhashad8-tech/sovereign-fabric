# Security Policy

## Supported versions

The `main` branch and the latest tagged release receive security fixes. Older
commits are not supported; reproduce against the latest `main`.

## Reporting a vulnerability

Report privately through the repository's **Security Advisories** tab. If that
is unavailable, open an issue that asks for a private channel and contains no
exploit details.

Include:

- the affected commit,
- a minimal reproduction,
- the impact you believe it has,
- any suggested fix or mitigation.

Do not include real credentials, personal data, or third-party secrets in a
report. Redact them.

## Disclosure timeline

- Acknowledgement within 72 hours.
- Triage and severity within 7 days.
- Fix for critical/high issues within 30 days where feasible.
- A public disclosure report after the fix, naming the issue, impact, fix, and
  prevention measure.

## Scope

- `sovereign/` source and the FastAPI service.
- Guardian adapters and their parsing.
- Capability synthesis and the subprocess gate.
- The dependency chain declared in `pyproject.toml`.

Out of scope: social engineering, denial of service against third-party
services, and vulnerabilities in optional external model providers.

## Automated checks

```bash
python -m pytest
python -m sovereign audit --strict      # static rules + licences + OSV
python -m sovereign disclosure          # writes SECURITY_DISCLOSURE.md
python -m sovereign openness            # writes OPENNESS_MANIFEST.json
```

The audit fails closed: a high/critical finding, an unknown licence, a known
OSV vulnerability, or a missing licence file makes `--strict` exit non-zero.
