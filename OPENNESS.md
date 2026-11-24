# Openness

## Licence

The source is released under the MIT licence. See `LICENSE`.

## Runtime dependencies

The project uses open-source libraries only. The direct dependencies are:

| Package | Licence |
| --- | --- |
| fastapi | MIT |
| uvicorn | BSD-3-Clause |
| httpx | BSD-3-Clause |
| pytest (dev) | MIT |

Transitive dependencies are resolved and classified by
`python -m sovereign audit`. The audit fails if any resolved dependency has an
unknown or non-open licence.

## Optional external experts

The optional expert path talks to an OpenAI-compatible HTTP endpoint. That is a
service, not a linked library; it is disabled unless configured. If enabled,
the prompt and the response leave this machine. The code that calls it remains
MIT-licensed, and the system works without it using the local corpus and the
other guardians.

## Reproduce the audit

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m sovereign audit --strict
python -m sovereign disclosure
python -m sovereign openness
python -m sovereign sbom
```

The audit:

- parses every Python file under `sovereign/` with `ast`,
- flags dynamic code, shell execution, unsafe deserialization, weak hashes,
  disabled TLS verification, SQL string building, hardcoded secrets, plaintext
  HTTP, and swallowed exceptions,
- resolves direct and transitive requirements and classifies their licences,
- queries OSV for known vulnerabilities in the resolved versions,
- runs in-process DAST checks (`tests/test_dast.py`),
- writes `SECURITY_DISCLOSURE.md`, `OPENNESS_MANIFEST.json`, and a CycloneDX
  1.5 `sbom.cdx.json`.

## What is public and what is not

Public: all source, tests, the scanner, the DAST checks, the disclosure
report, the manifest, the SBOM, the threat model, and the dependency list.

Not public: the hosted runtime, optional model weights behind an external
provider, and any user data. No user data is required to run the project.

## Community review

Pull requests are welcome. A change is mergeable only when the tests pass, the
strict audit passes, and the change is reviewable as a small diff. Signed
commits are recommended; they are not enforced by this repository.
