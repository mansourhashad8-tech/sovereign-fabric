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
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Callable, Protocol

from ..models import KnowledgeUnit, Provenance, utcnow
from ..store import FabricStore

USER_AGENT = "sovereign-fabric/0.1 (research; contact: local)"
MAX_RESPONSE_BYTES = 2_000_000


def default_fetch(url: str, timeout: float = 6.0, max_bytes: int = MAX_RESPONSE_BYTES) -> str:
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError(f"refusing non-http(s) URL: {scheme or '(none)'}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        declared = resp.headers.get("Content-Length")
        if declared:
            try:
                if int(declared) > max_bytes:
                    raise ValueError(f"response declares {declared} bytes, limit is {max_bytes}")
            except ValueError:
                raise
        body = resp.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError(f"response exceeds {max_bytes} bytes")
        return body.decode("utf-8", "replace")


def stable_id(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
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
    duration_s: float = 0.0

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
    def __init__(
        self,
        guardians: list[Guardian],
        max_workers: int = 6,
        failure_cooldown: float = 30.0,
    ) -> None:
        self.guardians = {g.name: g for g in guardians}
        self.max_workers = max_workers
        self.failure_cooldown = failure_cooldown
        self._failed_at: dict[str, float] = {}
        self._lock = threading.Lock()

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
        deadline_s: float | None = None,
    ) -> ConsultationResult:
        started = time.monotonic()
        selected = [s for s in (sources or self.names()) if s in self.guardians]
        status: dict[str, str] = {}
        collected: list[KnowledgeUnit] = []
        ready: list[str] = []
        now = time.monotonic()
        for name in selected:
            with self._lock:
                failed_at = self._failed_at.get(name)
            if failed_at is not None and now - failed_at < self.failure_cooldown:
                status[name] = "cooldown"
            else:
                ready.append(name)

        def run(name: str) -> tuple[str, str, list[KnowledgeUnit]]:
            try:
                units = self.guardians[name].search(query, limit)
            except Exception as exc:  # a dead source must not kill the consultation
                with self._lock:
                    self._failed_at[name] = time.monotonic()
                return name, f"error: {type(exc).__name__}: {exc}", []
            with self._lock:
                self._failed_at.pop(name, None)
            return name, "ok", units

        if parallel and len(ready) > 1:
            pool = ThreadPoolExecutor(max_workers=len(ready))
            futures = {pool.submit(run, name): name for name in ready}
            try:
                done, not_done = wait(futures, timeout=deadline_s)
                for future in done:
                    name, state, units = future.result()
                    status[name] = state
                    collected.extend(units)
                for future in not_done:
                    status[futures[future]] = "timeout"
            finally:
                pool.shutdown(wait=deadline_s is None, cancel_futures=True)
        else:
            for name in ready:
                name, state, units = run(name)
                status[name] = state
                collected.extend(units)

        return ConsultationResult(
            query=query,
            units=_dedupe(collected),
            sources=status,
            duration_s=time.monotonic() - started,
        )


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
