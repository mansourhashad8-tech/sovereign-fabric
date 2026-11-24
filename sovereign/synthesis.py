"""Safe self-extension: generate a capability from a spec, verify, then admit.

The specification is a set of behavioural examples (input -> expected output),
which are independent of the implementation. A candidate is admitted only if
it reproduces every example inside a separate interpreter. A candidate that
fails is quarantined, not silently kept.

Scope is deliberately narrow: this is template synthesis over a small set of
operations, not general program synthesis. The gate is what makes it honest.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any

from .capabilities import CapabilityRegistry, _sanitized_env
from .models import Capability, Provenance

_TEMPLATES: dict[str, str] = {
    "identity": 'def run(payload):\n    return payload\n',
    "upper": 'def run(payload):\n    return {"value": str(payload.get("value", "")).upper()}\n',
    "lower": 'def run(payload):\n    return {"value": str(payload.get("value", "")).lower()}\n',
    "reverse": 'def run(payload):\n    return {"value": payload.get("value", "")[::-1]}\n',
    "length": 'def run(payload):\n    return {"value": len(payload.get("value", ""))}\n',
    "sum_list": 'def run(payload):\n    return {"value": sum(payload.get("value", []))}\n',
    "constant": (
        "def run(payload):\n"
        "    return {\"value\": _CONSTANT}\n"
    ),
}

_DRIVER = """\
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("capmod", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
with open(sys.argv[2], encoding="utf-8") as handle:
    examples = json.load(handle)
passed = failed = 0
failures = []
for index, (given, expected) in enumerate(examples):
    try:
        got = mod.run(given)
    except Exception as exc:
        failed += 1
        failures.append(f"example {index}: raised {type(exc).__name__}: {exc}")
        continue
    if got == expected:
        passed += 1
    else:
        failed += 1
        failures.append(f"example {index}: expected {expected!r} got {got!r}")
print(json.dumps({"passed": passed, "failed": failed, "failures": failures}))
"""


@dataclass
class SynthesisResult:
    admitted: bool
    reason: str
    passed: int = 0
    failed: int = 0
    failures: list[str] = field(default_factory=list)
    capability: Capability | None = None


class Synthesizer:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def source_for(self, spec: dict[str, Any]) -> str:
        if spec.get("source"):
            return str(spec["source"])
        op = spec.get("op", "")
        template = _TEMPLATES.get(op)
        if template is None:
            raise ValueError(f"no template for operation {op!r}")
        if op == "constant":
            template = template.replace("_CONSTANT", json.dumps(spec.get("value")))
        return template

    def verify(self, source: str, examples: list[Any], timeout: float = 15.0) -> SynthesisResult:
        if not examples:
            return SynthesisResult(admitted=False, reason="no examples to verify against")
        with tempfile.TemporaryDirectory() as workdir:
            module_path = os.path.join(workdir, "capmod.py")
            driver_path = os.path.join(workdir, "driver.py")
            examples_path = os.path.join(workdir, "examples.json")
            with open(module_path, "w", encoding="utf-8") as handle:
                handle.write(source)
            with open(driver_path, "w", encoding="utf-8") as handle:
                handle.write(_DRIVER)
            with open(examples_path, "w", encoding="utf-8") as handle:
                json.dump(examples, handle)
            try:
                proc = subprocess.run(
                    [sys.executable, driver_path, module_path, examples_path],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=workdir,
                    env=_sanitized_env(),
                )
            except subprocess.TimeoutExpired:
                return SynthesisResult(
                    admitted=False, reason=f"verification timed out after {timeout}s"
                )
            if proc.returncode != 0:
                return SynthesisResult(
                    admitted=False,
                    reason=f"verification process exited {proc.returncode}: "
                    f"{proc.stderr.strip()[:300]}",
                )
            try:
                data = json.loads(proc.stdout.strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError):
                return SynthesisResult(admitted=False, reason="unparseable verification output")
        passed, failed = int(data["passed"]), int(data["failed"])
        ok = failed == 0 and passed > 0
        reason = (
            f"all {passed} examples reproduced"
            if ok
            else f"{failed} of {passed + failed} examples failed"
        )
        return SynthesisResult(
            admitted=ok, reason=reason, passed=passed, failed=failed,
            failures=list(data.get("failures", [])),
        )

    def synthesize(
        self,
        name: str,
        description: str,
        inputs: tuple[str, ...],
        outputs: tuple[str, ...],
        spec: dict[str, Any],
        examples: list[Any],
    ) -> SynthesisResult:
        try:
            source = self.source_for(spec)
        except ValueError as exc:
            return SynthesisResult(admitted=False, reason=str(exc))
        result = self.verify(source, examples)
        capability = Capability(
            name=name,
            description=description,
            inputs=inputs,
            outputs=outputs,
            kind="synthesized",
            entry=source,
            provenance=Provenance(
                source="synthesis",
                url="",
                license="internal",
                confidence=1.0 if result.admitted else 0.2,
            ),
            spec={"op": spec.get("op", "custom"), "examples": len(examples)},
        )
        registered = self.registry.register(capability, activate=result.admitted)
        result.capability = registered
        self.registry.store.record_event(
            "capability.synthesized",
            {
                "name": name,
                "version": registered.version,
                "admitted": result.admitted,
                "reason": result.reason,
                "passed": result.passed,
                "failed": result.failed,
            },
        )
        return result
