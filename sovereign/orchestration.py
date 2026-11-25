"""Sovereign orchestration over real external media.

The orchestrator plans a DAG, selects a provider by capability and probed
status, executes bounded tasks, applies a declared quality gate, and reassigns
failed work once. It never invents a provider, an account, or a successful
remote run. Heavy work is never assigned to the local control plane.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .providers import DEFAULT_REPO, ProviderRegistry
from .quality import STANDARDS, QualityGate
from .store import FabricStore


@dataclass
class Task:
    id: str
    capability: str
    payload: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    standard: str = "schema"
    heavy: bool = True
    kind: str = "external"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Task":
        return cls(
            id=str(value["id"]),
            capability=str(value["capability"]),
            payload=dict(value.get("payload") or {}),
            depends_on=tuple(value.get("depends_on") or ()),
            standard=str(value.get("standard") or "schema"),
            heavy=bool(value.get("heavy", True)),
            kind=str(value.get("kind") or "external"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "capability": self.capability,
            "payload": self.payload,
            "depends_on": list(self.depends_on),
            "standard": self.standard,
            "heavy": self.heavy,
            "kind": self.kind,
        }


class GitHubActionsAdapter:
    id = "github-actions"

    def __init__(
        self,
        repo: str = DEFAULT_REPO,
        token: str | None = None,
        timeout_s: float = 300.0,
        poll_s: float = 5.0,
        client: Any = None,
    ) -> None:
        self.repo = repo
        self.token = token
        self.timeout_s = timeout_s
        self.poll_s = poll_s
        self.client = client

    def _headers(self) -> dict[str, str]:
        import os

        token = self.token or os.environ.get("GITHUB_WRITE_TOKEN", "")
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        if self.client is not None:
            return self.client.request(method, url, **kwargs)
        import httpx

        return httpx.request(method, url, **kwargs)

    def _find_run(self, dispatched_at: float) -> dict[str, Any] | None:
        url = (
            f"https://api.github.com/repos/{self.repo}/actions/workflows/"
            "remote-task.yml/runs?event=workflow_dispatch&per_page=10"
        )
        response = self._request("GET", url, headers=self._headers(), timeout=20)
        if response.status_code != 200:
            return None
        for run in response.json().get("workflow_runs", []):
            created = run.get("created_at", "")
            try:
                stamp = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
            except (ValueError, AttributeError):
                stamp = 0.0
            if stamp >= dispatched_at - 15:
                return run
        return None

    def run(self, task: Task) -> dict[str, Any]:
        name = str(task.payload.get("task", "tests"))
        if name not in {"tests", "audit", "both"}:
            return {
                "task_id": task.id,
                "provider": self.id,
                "status": "rejected",
                "conclusion": "unsupported_task",
                "evidence": {"allowed": ["tests", "audit", "both"]},
                "command": f"remote-task:{name}",
            }
        ref = str(task.payload.get("ref", "main"))
        if not ref.replace("-", "").replace("_", "").replace("/", "").isalnum():
            return {
                "task_id": task.id,
                "provider": self.id,
                "status": "rejected",
                "conclusion": "invalid_ref",
                "evidence": {"ref": ref},
                "command": f"remote-task:{name}",
            }
        dispatched_at = time.time()
        url = (
            f"https://api.github.com/repos/{self.repo}/actions/workflows/"
            "remote-task.yml/dispatches"
        )
        response = self._request(
            "POST",
            url,
            headers=self._headers(),
            json={"ref": ref, "inputs": {"task": name, "ref": ref}},
            timeout=30,
        )
        if response.status_code not in {201, 204}:
            return {
                "task_id": task.id,
                "provider": self.id,
                "status": "failed",
                "conclusion": f"dispatch_{response.status_code}",
                "evidence": {"dispatch_status": response.status_code},
                "command": f"remote-task:{name}",
            }
        run = None
        for _ in range(15):
            run = self._find_run(dispatched_at)
            if run is not None:
                break
            time.sleep(2.0)
        if run is None:
            return {
                "task_id": task.id,
                "provider": self.id,
                "status": "failed",
                "conclusion": "dispatch_not_observed",
                "evidence": {"dispatch_status": response.status_code},
                "command": f"remote-task:{name}",
            }
        run_id = run.get("id")
        deadline = time.monotonic() + self.timeout_s
        latest = run
        while time.monotonic() < deadline:
            status_url = f"https://api.github.com/repos/{self.repo}/actions/runs/{run_id}"
            poll = self._request("GET", status_url, headers=self._headers(), timeout=20)
            if poll.status_code != 200:
                return {
                    "task_id": task.id,
                    "provider": self.id,
                    "status": "failed",
                    "conclusion": f"poll_{poll.status_code}",
                    "run_id": run_id,
                    "evidence": {"run_id": run_id},
                    "command": f"remote-task:{name}",
                }
            latest = poll.json()
            if latest.get("status") == "completed":
                conclusion = latest.get("conclusion")
                return {
                    "task_id": task.id,
                    "provider": self.id,
                    "status": "ok" if conclusion == "success" else "failed",
                    "conclusion": conclusion,
                    "run_id": run_id,
                    "html_url": latest.get("html_url"),
                    "evidence": {
                        "remote_run": run_id,
                        "workflow": "remote-task.yml",
                        "conclusion": conclusion,
                        "head_sha": latest.get("head_sha"),
                        "task": name,
                    },
                    "command": f"remote-task:{name}",
                }
            time.sleep(self.poll_s)
        return {
            "task_id": task.id,
            "provider": self.id,
            "status": "timeout",
            "conclusion": "timeout",
            "run_id": run_id,
            "html_url": latest.get("html_url"),
            "evidence": {"run_id": run_id, "last_status": latest.get("status")},
            "command": f"remote-task:{name}",
        }


class HuggingFaceAdapter:
    id = "huggingface-hub"

    def __init__(self, token: str | None = None, timeout_s: float = 30.0, client: Any = None) -> None:
        self.token = token
        self.timeout_s = timeout_s
        self.client = client

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        if self.client is not None:
            return self.client.request(method, url, **kwargs)
        import httpx

        return httpx.request(method, url, **kwargs)

    def run(self, task: Task) -> dict[str, Any]:
        import os

        headers = {"Authorization": f"Bearer {self.token or os.environ.get('HF_TOKEN', '')}"}
        if task.capability in {"hub.metadata", "hub.models"}:
            query = str(task.payload.get("query", ""))
            limit = max(1, min(int(task.payload.get("limit", 5)), 20))
            response = self._request(
                "GET",
                "https://huggingface.co/api/models",
                params={"search": query, "limit": limit},
                headers=headers,
                timeout=self.timeout_s,
            )
            if response.status_code != 200:
                return {
                    "task_id": task.id,
                    "provider": "huggingface-hub",
                    "status": "failed",
                    "conclusion": f"http_{response.status_code}",
                    "evidence": {"query": query, "http_status": response.status_code},
                    "command": "hf.models.search",
                }
            models = response.json()
            return {
                "task_id": task.id,
                "provider": "huggingface-hub",
                "status": "ok",
                "conclusion": "success",
                "evidence": {
                    "query": query,
                    "models": [m.get("id") for m in models][:limit],
                    "count": len(models),
                },
                "command": "hf.models.search",
            }
        response = self._request(
            "POST",
            "https://router.huggingface.co/v1/chat/completions",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "model": task.payload.get("model", "meta-llama/Llama-3.1-8B-Instruct"),
                "messages": task.payload.get("messages", [{"role": "user", "content": "OK"}]),
                "max_tokens": max(1, min(int(task.payload.get("max_tokens", 8)), 128)),
            },
            timeout=self.timeout_s,
        )
        if response.status_code == 200:
            body = response.json()
            return {
                "task_id": task.id,
                "provider": "huggingface-inference",
                "status": "ok",
                "conclusion": "success",
                "evidence": {"model": body.get("model"), "usage": body.get("usage")},
                "command": "hf.chat.completions",
            }
        conclusion = (
            "blocked_credits" if response.status_code == 402 else f"http_{response.status_code}"
        )
        return {
            "task_id": task.id,
            "provider": "huggingface-inference",
            "status": "failed",
            "conclusion": conclusion,
            "evidence": {"http_status": response.status_code},
            "command": "hf.chat.completions",
        }


class GroqAdapter:
    id = "groq"

    def __init__(self, token: str | None = None, timeout_s: float = 30.0, client: Any = None) -> None:
        self.token = token
        self.timeout_s = timeout_s
        self.client = client

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        if self.client is not None:
            return self.client.request(method, url, **kwargs)
        import httpx

        return httpx.request(method, url, **kwargs)

    def run(self, task: Task) -> dict[str, Any]:
        import os

        token = self.token or os.environ.get("GROQ_API_KEY", "")
        response = self._request(
            "POST",
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "model": task.payload.get("model", "llama-3.1-8b-instant"),
                "messages": task.payload.get("messages", [{"role": "user", "content": "OK"}]),
                "max_tokens": max(1, min(int(task.payload.get("max_tokens", 8)), 128)),
            },
            timeout=self.timeout_s,
        )
        if response.status_code == 200:
            body = response.json()
            return {
                "task_id": task.id,
                "provider": "groq",
                "status": "ok",
                "conclusion": "success",
                "evidence": {"model": body.get("model"), "usage": body.get("usage")},
                "command": "groq.chat.completions",
            }
        conclusion = (
            "expired_credential" if response.status_code == 401 else f"http_{response.status_code}"
        )
        return {
            "task_id": task.id,
            "provider": "groq",
            "status": "failed",
            "conclusion": conclusion,
            "evidence": {"http_status": response.status_code},
            "command": "groq.chat.completions",
        }


class LocalControlAdapter:
    id = "local-control"

    def run(self, task: Task) -> dict[str, Any]:
        return {
            "task_id": task.id,
            "provider": self.id,
            "status": "ok",
            "conclusion": "success",
            "evidence": {
                "control": task.capability,
                "heavy": False,
                "note": "local control plane only; no heavy computation was claimed",
            },
            "command": f"control:{task.capability}",
        }


class Orchestrator:
    def __init__(
        self,
        store: FabricStore,
        registry: ProviderRegistry | None = None,
        adapters: dict[str, Any] | None = None,
        quality: QualityGate | None = None,
    ) -> None:
        self.store = store
        self.registry = registry or ProviderRegistry.discover(probe=False)
        self.quality = quality or QualityGate()
        self.adapters = adapters or {
            "github-actions": GitHubActionsAdapter(repo=self.registry.repo),
            "huggingface-hub": HuggingFaceAdapter(),
            "huggingface-inference": HuggingFaceAdapter(),
            "groq": GroqAdapter(),
            "local-control": LocalControlAdapter(),
        }

    def providers(self, probe: bool = False) -> dict[str, Any]:
        if probe:
            self.registry = ProviderRegistry.discover(probe=True, repo=self.registry.repo)
        return self.registry.to_dict()

    def standards(self) -> dict[str, Any]:
        return {
            "standards": list(STANDARDS.values()),
            "note": "ISO and ACID are subset checks, not certifications; ZKP requires a verifier",
        }

    def _topological(self, tasks: list[Task]) -> tuple[list[Task], list[str]]:
        by_id = {task.id: task for task in tasks}
        errors: list[str] = []
        if len(by_id) != len(tasks):
            errors.append("duplicate task ids")
        for task in tasks:
            for dep in task.depends_on:
                if dep not in by_id:
                    errors.append(f"{task.id} depends on missing {dep}")
        indegree = {task.id: len(task.depends_on) for task in tasks}
        children: dict[str, list[str]] = {task.id: [] for task in tasks}
        for task in tasks:
            for dep in task.depends_on:
                if dep in children:
                    children[dep].append(task.id)
        queue = [task.id for task in tasks if indegree[task.id] == 0]
        ordered: list[str] = []
        while queue:
            current = queue.pop(0)
            ordered.append(current)
            for child in children[current]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if len(ordered) != len(tasks):
            errors.append("dependency cycle detected")
        return [by_id[item] for item in ordered], errors

    def plan(self, tasks: list[Task]) -> dict[str, Any]:
        ordered, errors = self._topological(tasks)
        assignments: list[dict[str, Any]] = []
        for task in ordered:
            provider, reasons = self.registry.select(task.capability, task.heavy)
            assignments.append(
                {
                    "task": task.to_dict(),
                    "provider": provider.to_dict() if provider else None,
                    "status": "assigned" if provider else "blocked",
                    "reasons": reasons,
                }
            )
        blocked = [item for item in assignments if item["status"] == "blocked"]
        return {
            "ok": not errors and not blocked,
            "assignments": assignments,
            "blocked": blocked,
            "errors": errors,
            "order": [task.id for task in ordered],
            "note": "heavy tasks require an external provider; local control is never substituted",
        }

    def run(self, tasks: list[Task], max_replacements: int = 1) -> dict[str, Any]:
        max_replacements = max(0, min(max_replacements, 3))
        plan = self.plan(tasks)
        if not plan["ok"]:
            return {
                "status": "blocked",
                "plan": plan,
                "results": [],
                "note": "no eligible external provider for one or more tasks",
            }
        results: list[dict[str, Any]] = []
        accepted: dict[str, bool] = {}
        for item in plan["assignments"]:
            task = Task.from_dict(item["task"])
            if any(not accepted.get(dep, False) for dep in task.depends_on):
                results.append(
                    {"task": task.to_dict(), "status": "blocked", "reason": "dependency did not pass"}
                )
                accepted[task.id] = False
                continue
            provider = self.registry.get(item["provider"]["id"]) if item["provider"] else None
            if provider is None:
                results.append({"task": task.to_dict(), "status": "blocked", "reason": "no provider"})
                accepted[task.id] = False
                continue
            tried: set[str] = set()
            final: dict[str, Any] | None = None
            for _ in range(max_replacements + 1):
                adapter = self.adapters.get(provider.id)
                if adapter is None:
                    final = {
                        "task_id": task.id,
                        "provider": provider.id,
                        "status": "failed",
                        "conclusion": "no_adapter",
                        "evidence": {"provider": provider.id},
                        "command": task.capability,
                    }
                else:
                    final = adapter.run(task)
                quality = self.quality.evaluate(task.to_dict(), final)
                final["quality"] = quality.to_dict()
                if final.get("status") == "ok" and quality.passed:
                    final["reassignment"] = {"tried": sorted(tried), "next": None, "reasons": []}
                    break
                tried.add(provider.id)
                next_provider, reasons = self.registry.select(
                    task.capability, task.heavy, exclude=tried
                )
                final["reassignment"] = {
                    "tried": sorted(tried),
                    "next": next_provider.id if next_provider else None,
                    "reasons": reasons,
                }
                if next_provider is None:
                    break
                provider = next_provider
            results.append(final or {"task": task.to_dict(), "status": "failed"})
            accepted[task.id] = bool(
                final
                and final.get("status") == "ok"
                and final.get("quality", {}).get("passed")
            )
        status = "ok" if results and all(accepted.values()) else "partial"
        self.store.record_event(
            "orchestration.run",
            {
                "status": status,
                "tasks": len(tasks),
                "accepted": sum(1 for value in accepted.values() if value),
                "providers": sorted({r.get("provider", "") for r in results if r.get("provider")}),
            },
        )
        return {
            "status": status,
            "plan": plan,
            "results": results,
            "accepted": sum(1 for value in accepted.values() if value),
            "total": len(tasks),
            "teardown": "remote runners are ephemeral; no persistent resource is left by this run",
        }

    def provision(
        self, provider_id: str, resource: str = "ephemeral-runner", ttl_s: int = 900
    ) -> dict[str, Any]:
        provider = self.registry.get(provider_id)
        if provider is None:
            return {"provisioned": False, "reason": f"unknown provider {provider_id!r}"}
        if provider_id == "github-actions":
            return {
                "provisioned": True,
                "provider": provider_id,
                "resource": resource,
                "mode": "ephemeral_ci_run",
                "account_creation": False,
                "ttl_s": max(60, min(int(ttl_s), 3600)),
                "teardown": "automatic after the workflow run",
                "note": "uses an existing account; it does not create a new GitHub account",
            }
        return {
            "provisioned": False,
            "provider": provider_id,
            "resource": resource,
            "account_creation": False,
            "reason": (
                "automatic account creation is not supported: provider signup requires "
                "a human, payment, or CAPTCHA; no such credential is present"
            ),
        }
