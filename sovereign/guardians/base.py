"""External guardianship: consulting outside sources of knowledge.

A Guardian is any adapter that turns an external source into KnowledgeUnits
with provenance attached. The registry consults guardians in parallel, caches
responses, rate-limits each source, and records per-source status so a dead
source degrades the result instead of failing the whole consultation.
"""

from __future__ import annotations

import hashlib
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Protocol

from ..models import KnowledgeUnit, Provenance, utcnow
from ..store import FabricStore

USER_AGENT = "sovereign-fabric/0.1 (research; contact: local)"


def default_fetch(url: str, timeout: float = 12.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def stable_id(*parts: str) -> str:
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


class RateLimiter:
    def __init__(self, min_interval: float = 0.0) -> None:
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


class Guardian(Protocol):
    name: str

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]: ...


@dataclass
class ConsultationResult:
    query: str
    units: list[KnowledgeUnit]
    sources: dict[str, str] = field(default_factory=dict)

    @property
    def ok_sources(self) -> list[str]:
        return [s for s, status in self.sources.items() if status == "ok"]


class HttpGuardian:
    """Base for JSON/XML guardians backed by an injectable fetcher.

    Tests inject a fetcher that returns recorded fixtures, exercising the real
    parsing and normalisation code without touching the network.
    """

    name = "http"
    base_confidence = 0.6
    min_interval = 0.0

    def __init__(
        self,
        fetch: Callable[[str], str] | None = None,
        store: FabricStore | None = None,
        cache_ttl: float = 3600.0,
        min_interval: float | None = None,
    ) -> None:
        self._fetch = fetch or default_fetch
        self.store = store
        self.cache_ttl = cache_ttl
        self._limiter = RateLimiter(self.min_interval if min_interval is None else min_interval)

    def _get(self, url: str) -> str:
        key = f"{self.name}:{url}"
        if self.store is not None:
            cached = self.store.cache_get(key, self.cache_ttl)
            if cached is not None:
                return cached
        self._limiter.acquire()
        body = self._fetch(url)
        if self.store is not None:
            self.store.cache_set(key, body)
        return body

    def _unit(
        self,
        *,
        title: str,
        summary: str,
        url: str,
        concepts: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
        confidence: float | None = None,
        license: str = "",
        retrieved_at: str | None = None,
    ) -> KnowledgeUnit:
        return KnowledgeUnit(
            id=stable_id(self.name, url, title),
            title=" ".join(title.split()),
            summary=" ".join(summary.split()),
            provenance=Provenance(
                source=self.name,
                url=url,
                retrieved_at=retrieved_at or utcnow(),
                license=license,
                confidence=self.base_confidence if confidence is None else confidence,
            ),
            concepts=concepts,
            tags=tags,
        )

    def search(self, query: str, limit: int = 5) -> list[KnowledgeUnit]:  # pragma: no cover
        raise NotImplementedError


class GuardianRegistry:
    def __init__(self, guardians: list[Guardian], max_workers: int = 6) -> None:
        self.guardians = {g.name: g for g in guardians}
        self.max_workers = max_workers

    def register(self, guardian: Guardian) -> None:
        self.guardians[guardian.name] = guardian

    def names(self) -> list[str]:
        return sorted(self.guardians)

    def consult(
        self,
        query: str,
        limit: int = 5,
        sources: list[str] | None = None,
        parallel: bool = True,
    ) -> ConsultationResult:
        selected = [s for s in (sources or self.names()) if s in self.guardians]
        status: dict[str, str] = {}
        collected: list[KnowledgeUnit] = []

        def run(name: str) -> tuple[str, str, list[KnowledgeUnit]]:
            try:
                return name, "ok", self.guardians[name].search(query, limit)
            except Exception as exc:  # a dead source must not kill the consultation
                return name, f"error: {type(exc).__name__}: {exc}", []

        if parallel and len(selected) > 1:
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(selected))) as pool:
                results = list(pool.map(run, selected))
        else:
            results = [run(name) for name in selected]

        for name, state, units in results:
            status[name] = state
            collected.extend(units)

        return ConsultationResult(query=query, units=_dedupe(collected), sources=status)


def _dedupe(units: list[KnowledgeUnit]) -> list[KnowledgeUnit]:
    seen: set[str] = set()
    out: list[KnowledgeUnit] = []
    for unit in units:
        key = unit.provenance.url.strip().lower() or unit.title.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(unit)
    return out


def quote(query: str) -> str:
    return urllib.parse.quote_plus(query)
