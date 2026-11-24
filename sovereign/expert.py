"""External expert guardians.

The system can recruit other models as experts: it asks them for candidate
implementations, then admits one only if its own verification gate can
reproduce every example. Experts are optional and pluggable. If none is
reachable, acquisition reports that plainly and falls back to templates.

Nothing an expert returns is trusted. Its output is a *candidate*, and the
same subprocess gate that checks generated code checks it.
"""

from __future__ import annotations

import os
import re
from typing import Protocol

import httpx


class ExpertError(RuntimeError):
    pass


class Expert(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


_FENCE = re.compile(r"```(?:python|py)?\s*(.*?)```", re.S)


def extract_code(text: str) -> str:
    if not text:
        return ""
    match = _FENCE.search(text)
    return (match.group(1) if match else text).strip()


def code_prompt(description: str, examples, failures=None) -> tuple[str, str]:
    system = (
        "You write small, safe Python modules. Reply with one fenced python "
        "code block and nothing else."
    )
    lines = [f"Define run(payload: dict) -> dict that {description}.", "It must satisfy:"]
    for given, expected in examples:
        lines.append(f"- run({given!r}) == {expected!r}")
    if failures:
        lines.append("Previous attempts failed:")
        for failure in failures[-3:]:
            lines.append(f"- {failure}")
    lines.append("Use only the Python standard library. Return only the code.")
    return system, "\n".join(lines)


class OpenAICompatExpert:
    """Any OpenAI-compatible chat endpoint (Groq, OpenAI, local servers)."""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        post=None,
        timeout: float = 30.0,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._post = post or self._http_post

    def _http_post(self, url: str, headers: dict, payload: dict) -> dict:
        response = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def complete(self, system: str, user: str) -> str:
        if not self.api_key:
            raise ExpertError(f"{self.name}: no api key")
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = self._post(
            f"{self.base_url}/chat/completions",
            {"Authorization": f"Bearer {self.api_key}"},
            payload,
        )
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ExpertError(f"{self.name}: unexpected response shape") from exc


class GroqExpert(OpenAICompatExpert):
    def __init__(self, api_key=None, model=None, post=None, timeout: float = 30.0) -> None:
        super().__init__(
            "groq",
            "https://api.groq.com/openai/v1",
            api_key if api_key is not None else os.environ.get("GROQ_API_KEY", ""),
            model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            post,
            timeout,
        )


class OpenAIExpert(OpenAICompatExpert):
    def __init__(
        self, api_key=None, model=None, base_url=None, post=None, timeout: float = 30.0
    ) -> None:
        super().__init__(
            "openai",
            base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", ""),
            model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            post,
            timeout,
        )


class EnsembleExpert:
    """Several experts treated as one source of many candidate answers."""

    def __init__(self, experts: list[Expert]) -> None:
        self.experts = list(experts)
        self.name = "ensemble"

    def complete(self, system: str, user: str) -> str:
        for expert in self.experts:
            try:
                return expert.complete(system, user)
            except Exception:
                continue
        raise ExpertError("all experts failed")

    def complete_all(self, system: str, user: str) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        for expert in self.experts:
            try:
                results.append((expert.name, expert.complete(system, user)))
            except Exception:
                results.append((expert.name, ""))
        return results


def default_experts() -> list[Expert]:
    experts: list[Expert] = []
    if os.environ.get("GROQ_API_KEY"):
        experts.append(GroqExpert())
    if os.environ.get("OPENAI_API_KEY"):
        experts.append(OpenAIExpert())
    return experts
