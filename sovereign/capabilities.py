"""Capability registry: versioned admission, hot-swap, rollback, invocation.

Built-ins run in-process. Synthesized capabilities are stored as source and
run in a separate interpreter with a timeout and a sanitized environment, so
generated code cannot read secrets or hang the caller.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
from typing import Any

from .models import Capability, Provenance
from .native import NATIVE
from .store import FabricStore

_SENSITIVE = ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "APIKEY", "API_KEY")

_RUNNER = """\
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("capmod", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
payload = json.load(sys.stdin)
json.dump({"ok": True, "result": mod.run(payload)}, sys.stdout, default=str)
"""


class CapabilityError(RuntimeError):
    pass


def _sanitized_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in _SENSITIVE)
    }


class CapabilityRegistry:
    def __init__(self, store: FabricStore) -> None:
        self.store = store

    def register(
        self,
        capability: Capability,
        version: int | None = None,
        activate: bool = True,
    ) -> Capability:
        capability.version = version if version is not None else self.store.next_version(capability.name)
        capability.status = "admitted" if activate else "quarantined"
        self.store.save_capability(capability)
        self.store.record_event(
            "capability.registered",
            {
                "name": capability.name,
                "version": capability.version,
                "kind": capability.kind,
                "status": capability.status,
            },
        )
        return capability

    def get(self, name: str, version: int | None = None) -> Capability | None:
        return self.store.get_capability(name, version)

    def active(self, name: str) -> Capability | None:
        for cap in sorted(
            self.store.list_capabilities(status="admitted"),
            key=lambda c: c.version,
            reverse=True,
        ):
            if cap.name == name:
                return cap
        return None

    def list_active(self) -> list[Capability]:
        latest: dict[str, Capability] = {}
        for cap in self.store.list_capabilities(status="admitted"):
            current = latest.get(cap.name)
            if current is None or cap.version > current.version:
                latest[cap.name] = cap
        return [latest[name] for name in sorted(latest)]

    def quarantine(self, name: str, version: int) -> bool:
        return self.store.set_capability_status(name, version, "quarantined")

    def rollback(self, name: str) -> Capability | None:
        current = self.active(name)
        if current is None:
            return None
        self.store.set_capability_status(name, current.version, "rolled_back")
        self.store.record_event(
            "capability.rolled_back", {"name": name, "version": current.version}
        )
        return self.active(name)

    def invoke(
        self, name: str, payload: dict[str, Any], timeout: float = 10.0
    ) -> Any:
        capability = self.active(name)
        if capability is None:
            raise CapabilityError(f"no active capability named {name!r}")
        if capability.kind == "builtin":
            return self._invoke_builtin(capability, payload)
        return self._invoke_sandboxed(capability, payload, timeout)

    def _invoke_builtin(self, capability: Capability, payload: dict[str, Any]) -> Any:
        module_name, _, func_name = capability.entry.partition(":")
        module = importlib.import_module(module_name)
        func = getattr(module, func_name, None)
        if func is None:
            raise CapabilityError(f"{capability.entry} is not callable")
        try:
            return func(payload)
        except Exception as exc:
            raise CapabilityError(f"{capability.id} failed: {exc}") from exc

    def _invoke_sandboxed(
        self, capability: Capability, payload: dict[str, Any], timeout: float
    ) -> Any:
        with tempfile.TemporaryDirectory() as workdir:
            module_path = os.path.join(workdir, "capmod.py")
            runner_path = os.path.join(workdir, "runner.py")
            with open(module_path, "w", encoding="utf-8") as handle:
                handle.write(capability.entry)
            with open(runner_path, "w", encoding="utf-8") as handle:
                handle.write(_RUNNER)
            try:
                proc = subprocess.run(
                    [sys.executable, runner_path, module_path],
                    input=json.dumps(payload),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=workdir,
                    env=_sanitized_env(),
                )
            except subprocess.TimeoutExpired as exc:
                raise CapabilityError(f"{capability.id} timed out after {timeout}s") from exc
            if proc.returncode != 0:
                raise CapabilityError(
                    f"{capability.id} exited {proc.returncode}: {proc.stderr.strip()[:400]}"
                )
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                raise CapabilityError(f"{capability.id} produced invalid output") from exc
            if not data.get("ok"):
                raise CapabilityError(f"{capability.id} reported failure")
            return data["result"]


NATIVE_SPEC = (
    ("text.tokenize", "tokenize", "Split text into tokens", ("text",), ("tokens",)),
    ("tokens.count", "count_tokens", "Count token frequencies", ("tokens",), ("counts",)),
    ("counts.summarize", "summarize_counts", "Summarize counts into a report", ("counts",), ("report",)),
    ("report.format", "format_report", "Render a report as markdown", ("report",), ("markdown",)),
    ("text.summarize", "extractive_summary", "Extractive one-sentence summary", ("text",), ("summary",)),
)


def bootstrap_native(registry: CapabilityRegistry) -> None:
    """Admit each native capability once; a quarantined name can return."""
    for name, func, description, inputs, outputs in NATIVE_SPEC:
        if registry.active(name) is not None:
            continue
        registry.register(
            Capability(
                name=name,
                description=description,
                inputs=inputs,
                outputs=outputs,
                kind="builtin",
                entry=f"sovereign.native:{func}",
                provenance=Provenance(source="builtin", url="", license="internal", confidence=1.0),
            )
        )
