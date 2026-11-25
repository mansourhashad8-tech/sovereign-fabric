"""Strict quality gates for external artifacts.

Standards are applied only when a task declares them. A gate can fail, pass,
or be not applicable; it never turns missing evidence into a pass. ISO and
ACID checks are subset checks, not certifications, and the ZKP gate requires a
cryptographic verifier result rather than a structural lookalike.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .validator import HolisticValidator

STANDARDS: dict[str, dict[str, Any]] = {
    "schema": {
        "name": "schema",
        "description": "artifact is a JSON object with a status and evidence",
        "scope": "all external artifacts",
    },
    "reproducibility": {
        "name": "reproducibility",
        "description": "artifact identifies the remote run, conclusion, and command",
        "scope": "remote execution",
    },
    "ACID": {
        "name": "ACID",
        "description": "atomicity, consistency, isolation, and durability evidence",
        "scope": "database tasks",
    },
    "ISO_25010_subset": {
        "name": "ISO_25010_subset",
        "description": "functional, reliability, security, and maintainability evidence",
        "scope": "engineering tasks; subset, not a certification",
    },
    "ZKP": {
        "name": "ZKP",
        "description": "proof, public signals, and a passing cryptographic verifier",
        "scope": "zero-knowledge proof artifacts",
    },
}


@dataclass
class QualityResult:
    standard: str
    passed: bool
    applicable: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "standard": self.standard,
            "passed": self.passed,
            "applicable": self.applicable,
            "checks": self.checks,
            "failures": self.failures,
            "note": self.note,
        }


class QualityGate:
    def __init__(self, validator: HolisticValidator | None = None) -> None:
        self.validator = validator or HolisticValidator()

    def evaluate(self, task: dict[str, Any], result: dict[str, Any]) -> QualityResult:
        standard = str(task.get("standard") or "schema")
        checks: list[dict[str, Any]] = []
        failures: list[str] = []

        def check(name: str, ok: bool, detail: str, applicable: bool = True) -> None:
            checks.append(
                {"name": name, "passed": bool(ok), "applicable": applicable, "detail": detail}
            )
            if applicable and not ok:
                failures.append(f"{name}: {detail}")

        if standard not in STANDARDS:
            return QualityResult(
                standard=standard,
                passed=False,
                applicable=True,
                checks=[],
                failures=[f"unknown standard {standard!r}"],
                note="unknown standards are rejected",
            )

        if not isinstance(result, dict):
            return QualityResult(
                standard=standard,
                passed=False,
                applicable=True,
                failures=["result is not an object"],
            )

        check("object", True, "result is a JSON object")
        check(
            "status",
            result.get("status") in {"ok", "success", "completed"}
            or result.get("conclusion") == "success",
            f"status={result.get('status')!r}, conclusion={result.get('conclusion')!r}",
        )
        evidence = result.get("evidence")
        check(
            "evidence",
            bool(evidence),
            "evidence must be present and non-empty",
        )

        text = json.dumps(result, ensure_ascii=False, default=str)[:20000]
        overclaims = self.validator.detect_overclaims(text)
        check("no_overclaim", not overclaims, "; ".join(overclaims) or "no overclaims detected")

        if standard == "reproducibility":
            check("run_id", bool(result.get("run_id")), "remote run id is required")
            check(
                "conclusion",
                result.get("conclusion") == "success",
                f"conclusion={result.get('conclusion')!r}",
            )
            check(
                "command",
                bool(result.get("command") or task.get("payload", {}).get("task")),
                "command or bounded task name is required",
            )
        elif standard == "ACID":
            evidence = result.get("evidence") or {}
            for key in ("atomic", "consistent", "isolated", "durable"):
                check(f"acid.{key}", bool(evidence.get(key)), f"{key} evidence is required")
        elif standard == "ISO_25010_subset":
            evidence = result.get("evidence") or {}
            for key in ("functional", "reliability", "security", "maintainability"):
                check(
                    f"iso.{key}",
                    bool(evidence.get(key)),
                    f"{key} evidence is required for the subset check",
                )
        elif standard == "ZKP":
            evidence = result.get("evidence") or {}
            check("zkp.proof", bool(evidence.get("proof")), "proof is required")
            check(
                "zkp.public_signals",
                bool(evidence.get("public_signals")),
                "public signals are required",
            )
            verifier = evidence.get("verifier_result") or {}
            check(
                "zkp.verifier",
                bool(verifier.get("verified")),
                "a passing cryptographic verifier result is required",
            )

        passed = not failures
        return QualityResult(
            standard=standard,
            passed=passed,
            applicable=True,
            checks=checks,
            failures=failures,
            note=(
                "all applicable checks passed"
                if passed
                else "one or more applicable checks failed"
            ),
        )
