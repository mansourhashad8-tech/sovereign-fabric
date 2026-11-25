"""External professional media discovery with explicit, probed statuses.

A provider is only usable when its credential exists and a probe succeeds. The
local interpreter is a control plane, not a heavy-compute substitute; heavy
tasks are never assigned to it.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

DEFAULT_REPO = "mansourhashad8-tech/sovereign-fabric"


@dataclass
class Provider:
    id: str
    name: str
    capabilities: tuple[str, ...]
    credential_env: str
    endpoint: str
    status: str = "unknown"
    detail: str = ""
    heavy: bool = False
    max_parallel: int = 1
    cost_per_min: float = 0.0
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.status in {"ready", "configured"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "capabilities": list(self.capabilities),
            "credential_env": self.credential_env,
            "endpoint": self.endpoint,
            "status": self.status,
            "detail": self.detail,
            "heavy": self.heavy,
            "max_parallel": self.max_parallel,
            "cost_per_min": self.cost_per_min,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
            "ready": self.ready,
        }


def _has(name: str) -> bool:
    return bool(os.environ.get(name))


def _providers(repo: str) -> list[Provider]:
    return [
        Provider(
            id="github-actions",
            name="GitHub Actions",
            capabilities=("compute.python", "compute.pytest", "compute.audit", "ci.run"),
            credential_env="GITHUB_WRITE_TOKEN",
            endpoint=f"https://api.github.com/repos/{repo}/actions",
            status="configured" if _has("GITHUB_WRITE_TOKEN") else "missing_credential",
            detail="bounded workflow_dispatch runner; ephemeral compute",
            heavy=True,
            max_parallel=1,
            cost_per_min=0.0,
            latency_ms=1500,
            metadata={"repo": repo, "workflow": "remote-task.yml"},
        ),
        Provider(
            id="huggingface-hub",
            name="Hugging Face Hub",
            capabilities=("hub.metadata", "hub.models", "storage.artifact"),
            credential_env="HF_TOKEN",
            endpoint="https://huggingface.co/api",
            status="configured" if _has("HF_TOKEN") else "missing_credential",
            detail="metadata and artifact access; no inference claim",
            heavy=False,
            max_parallel=4,
            cost_per_min=0.0,
            latency_ms=300,
        ),
        Provider(
            id="huggingface-inference",
            name="Hugging Face Inference Providers",
            capabilities=("inference.chat",),
            credential_env="HF_TOKEN",
            endpoint="https://router.huggingface.co/v1/chat/completions",
            status="configured" if _has("HF_TOKEN") else "missing_credential",
            detail="external inference; probe reports credit or quota state",
            heavy=False,
            max_parallel=4,
            cost_per_min=0.0,
            latency_ms=800,
        ),
        Provider(
            id="groq",
            name="Groq",
            capabilities=("inference.chat",),
            credential_env="GROQ_API_KEY",
            endpoint="https://api.groq.com/openai/v1",
            status="configured" if _has("GROQ_API_KEY") else "missing_credential",
            detail="external inference; probe reports expired keys",
            heavy=False,
            max_parallel=4,
            cost_per_min=0.0,
            latency_ms=400,
        ),
        Provider(
            id="local-control",
            name="Local control plane",
            capabilities=("control.plan", "control.qa", "control.store"),
            credential_env="",
            endpoint="in-process",
            status="ready",
            detail="planning and quality control only; never assigned heavy tasks",
            heavy=False,
            max_parallel=1,
            cost_per_min=0.0,
            latency_ms=1,
        ),
    ]


def _probe_github(provider: Provider, repo: str, timeout: float = 15.0) -> None:
    if provider.status == "missing_credential":
        return
    import httpx

    token = os.environ["GITHUB_WRITE_TOKEN"]
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        response = httpx.get(
            f"https://api.github.com/repos/{repo}", headers=headers, timeout=timeout
        )
        if response.status_code == 200:
            workflow = httpx.get(
                f"https://api.github.com/repos/{repo}/actions/workflows/remote-task.yml",
                headers=headers,
                timeout=timeout,
            )
            if workflow.status_code == 200:
                provider.status = "ready"
                provider.detail = "repo reachable and remote-task workflow present"
            else:
                provider.status = "workflow_missing"
                provider.detail = f"workflow lookup returned {workflow.status_code}"
        elif response.status_code in {401, 403}:
            provider.status = "unauthorized"
            provider.detail = f"repo lookup returned {response.status_code}"
        else:
            provider.status = "unreachable"
            provider.detail = f"repo lookup returned {response.status_code}"
    except Exception as exc:  # network failure is a status, not a crash
        provider.status = "unreachable"
        provider.detail = f"{type(exc).__name__}: {str(exc)[:120]}"


def _probe_hf_hub(provider: Provider, timeout: float = 15.0) -> None:
    if provider.status == "missing_credential":
        return
    import httpx

    try:
        response = httpx.get(
            "https://huggingface.co/api/whoami-v2",
            headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}"},
            timeout=timeout,
        )
        if response.status_code == 200:
            provider.status = "ready"
            provider.detail = "token valid for Hub API"
        elif response.status_code in {401, 403}:
            provider.status = "unauthorized"
            provider.detail = f"whoami returned {response.status_code}"
        else:
            provider.status = "unreachable"
            provider.detail = f"whoami returned {response.status_code}"
    except Exception as exc:
        provider.status = "unreachable"
        provider.detail = f"{type(exc).__name__}: {str(exc)[:120]}"


def _probe_hf_inference(provider: Provider, timeout: float = 30.0) -> None:
    if provider.status == "missing_credential":
        return
    import httpx

    try:
        response = httpx.post(
            provider.endpoint,
            headers={
                "Authorization": f"Bearer {os.environ['HF_TOKEN']}",
                "Content-Type": "application/json",
            },
            json={
                "model": "meta-llama/Llama-3.1-8B-Instruct",
                "messages": [{"role": "user", "content": "Reply with OK"}],
                "max_tokens": 1,
            },
            timeout=timeout,
        )
        if response.status_code == 200:
            provider.status = "ready"
            provider.detail = "inference probe returned 200"
        elif response.status_code == 402:
            provider.status = "blocked_credits"
            provider.detail = "provider requires pre-paid credits or PRO"
        elif response.status_code in {401, 403}:
            provider.status = "unauthorized"
            provider.detail = f"inference probe returned {response.status_code}"
        elif response.status_code == 429:
            provider.status = "rate_limited"
            provider.detail = "inference probe returned 429"
        else:
            provider.status = "unavailable"
            provider.detail = f"inference probe returned {response.status_code}"
    except Exception as exc:
        provider.status = "unreachable"
        provider.detail = f"{type(exc).__name__}: {str(exc)[:120]}"


def _probe_groq(provider: Provider, timeout: float = 15.0) -> None:
    if provider.status == "missing_credential":
        return
    import httpx

    try:
        response = httpx.get(
            f"{provider.endpoint}/models",
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            timeout=timeout,
        )
        if response.status_code == 200:
            provider.status = "ready"
            provider.detail = "models endpoint returned 200"
        elif response.status_code == 401:
            provider.status = "expired_credential"
            provider.detail = "models endpoint rejected the key"
        elif response.status_code == 429:
            provider.status = "rate_limited"
            provider.detail = "models endpoint returned 429"
        else:
            provider.status = "unavailable"
            provider.detail = f"models endpoint returned {response.status_code}"
    except Exception as exc:
        provider.status = "unreachable"
        provider.detail = f"{type(exc).__name__}: {str(exc)[:120]}"


class ProviderRegistry:
    def __init__(self, providers: list[Provider] | None = None, repo: str = DEFAULT_REPO) -> None:
        self.repo = repo
        self.providers = providers or _providers(repo)

    @classmethod
    def discover(cls, probe: bool = False, repo: str = DEFAULT_REPO) -> "ProviderRegistry":
        registry = cls(repo=repo)
        if probe:
            for provider in registry.providers:
                if provider.id == "github-actions":
                    _probe_github(provider, repo)
                elif provider.id == "huggingface-hub":
                    _probe_hf_hub(provider)
                elif provider.id == "huggingface-inference":
                    _probe_hf_inference(provider)
                elif provider.id == "groq":
                    _probe_groq(provider)
        return registry

    def get(self, provider_id: str) -> Provider | None:
        return next((p for p in self.providers if p.id == provider_id), None)

    def candidates(
        self, capability: str, heavy: bool = False, exclude: set[str] | None = None
    ) -> list[Provider]:
        excluded = exclude or set()
        result = []
        for provider in self.providers:
            if provider.id in excluded:
                continue
            if capability not in provider.capabilities:
                continue
            if not provider.ready:
                continue
            if heavy and not provider.heavy:
                continue
            result.append(provider)
        return sorted(
            result,
            key=lambda p: (0 if p.id == "local-control" else 1, p.cost_per_min, p.latency_ms),
        )

    def select(
        self, capability: str, heavy: bool = False, exclude: set[str] | None = None
    ) -> tuple[Provider | None, list[dict[str, Any]]]:
        candidates = self.candidates(capability, heavy, exclude)
        reasons: list[dict[str, Any]] = []
        if candidates:
            return candidates[0], reasons
        for provider in self.providers:
            if provider.id in (exclude or set()):
                continue
            if capability not in provider.capabilities:
                continue
            if heavy and not provider.heavy:
                reason = "local provider is not allowed for heavy work"
            elif not provider.ready:
                reason = f"status is {provider.status}"
            else:
                reason = "not eligible"
            reasons.append({"provider": provider.id, "reason": reason})
        return None, reasons

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "providers": [provider.to_dict() for provider in self.providers],
            "probed_at": time.time(),
            "note": "configured means the credential exists; ready means a probe succeeded",
        }
