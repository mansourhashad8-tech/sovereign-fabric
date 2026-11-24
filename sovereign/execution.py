"""Execution engine: real parallelism, measured speed, cache, speculation.

Nothing here claims a speedup it did not measure. The engine runs the same
workload serially and in parallel, computes the ratio, and reports it. If
parallelism is slower (small batches, pickling overhead), it says so.

"Sub-millisecond" applies to in-memory cache hits, not to arbitrary execution.
Remote compute is a hook: with no configured endpoint it refuses rather than
pretending to have borrowed a supercomputer.
"""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Iterable

from .native import NATIVE
from .vectors import embed


class ExecutionError(RuntimeError):
    pass


class RemoteUnavailable(ExecutionError):
    pass


def _worker(task: tuple[str, str, Any]) -> Any:
    kind, ref, payload = task
    if kind == "native":
        return NATIVE[ref](payload)
    if kind == "source":
        namespace: dict[str, Any] = {}
        exec(ref, namespace)
        return namespace["run"](payload)
    raise ExecutionError(f"unknown execution kind {kind!r}")


@dataclass
class BatchResult:
    mode: str
    workers: int
    count: int
    duration_s: float
    serial_duration_s: float
    speedup: float
    throughput: float
    sample: list[Any] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "workers": self.workers,
            "count": self.count,
            "duration_s": round(self.duration_s, 9),
            "serial_duration_s": round(self.serial_duration_s, 9),
            "speedup": round(self.speedup, 3),
            "throughput_per_s": round(self.throughput, 1),
            "sample": self.sample,
            "note": self.note,
        }


class ExecutionEngine:
    def run_batch(
        self,
        kind: str,
        ref: str,
        payloads: Iterable[Any],
        mode: str = "auto",
        workers: int | None = None,
        baseline: bool = True,
    ) -> BatchResult:
        payloads = list(payloads)
        count = len(payloads)
        workers = workers or (os.cpu_count() or 1)
        if count == 0:
            return BatchResult("serial", workers, 0, 0.0, 0.0, 0.0, 0.0, [], "empty batch")
        if mode == "auto":
            mode = "processes" if count >= 64 and workers > 1 else "serial"
        if mode not in {"serial", "threads", "processes"}:
            raise ExecutionError(f"unknown mode {mode!r}")

        serial_duration = 0.0
        serial_results: list[Any] = []
        if baseline or mode == "serial":
            start = time.perf_counter()
            serial_results = [_worker((kind, ref, payload)) for payload in payloads]
            serial_duration = time.perf_counter() - start

        start = time.perf_counter()
        effective = mode
        if mode == "serial":
            results = serial_results
        elif mode == "threads":
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(
                    pool.map(_worker, ((kind, ref, p) for p in payloads))
                )
        else:
            chunksize = max(1, count // (workers * 4))
            try:
                with ProcessPoolExecutor(max_workers=workers) as pool:
                    results = list(
                        pool.map(
                            _worker,
                            ((kind, ref, p) for p in payloads),
                            chunksize=chunksize,
                        )
                    )
            except Exception as exc:  # sandbox without process support
                effective = f"threads (process pool unavailable: {type(exc).__name__})"
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    results = list(pool.map(_worker, ((kind, ref, p) for p in payloads)))
        duration = time.perf_counter() - start
        if mode == "serial":
            duration = serial_duration

        speedup = serial_duration / duration if duration > 0 else 0.0
        if effective == "serial":
            note = "serial baseline; no parallel claim"
        elif speedup < 1.05:
            note = "no parallel gain at this size; serial is as fast or faster"
        else:
            note = f"measured {speedup:.2f}x against serial on this machine"
        return BatchResult(
            mode=effective,
            workers=workers,
            count=count,
            duration_s=duration,
            serial_duration_s=serial_duration,
            speedup=speedup,
            throughput=count / duration if duration > 0 else 0.0,
            sample=results[:3],
            note=note,
        )

    def run_capability(
        self,
        registry,
        name: str,
        payloads: Iterable[Any],
        mode: str = "auto",
        workers: int | None = None,
        baseline: bool = True,
    ) -> BatchResult:
        capability = registry.get(name)
        if capability is None:
            raise ExecutionError(f"no such capability: {name}")
        if capability.kind == "builtin":
            kind, ref = "native", name
        else:
            kind, ref = "source", capability.entry
        return self.run_batch(kind, ref, payloads, mode, workers, baseline)


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    hit_latency_us: float = 0.0


class HotCache:
    """In-process, content-addressed cache. Hits are dict lookups."""

    def __init__(self, max_entries: int = 10000, ttl_s: float = 300.0) -> None:
        self.max_entries = max_entries
        self.ttl_s = ttl_s
        self._data: dict[Any, tuple[Any, float]] = {}
        self._latencies: list[float] = []
        self._lock = threading.Lock()
        self.stats = CacheStats()

    def get(self, key: Any) -> Any:
        start = time.perf_counter()
        with self._lock:
            item = self._data.get(key)
            if item is None or item[1] < time.time():
                if item is not None:
                    del self._data[key]
                self.stats.misses += 1
                return None
            self.stats.hits += 1
            self._latencies.append((time.perf_counter() - start) * 1e6)
            if len(self._latencies) > 1000:
                self._latencies = self._latencies[-1000:]
            self.stats.hit_latency_us = sum(self._latencies) / len(self._latencies)
            return item[0]

    def put(self, key: Any, value: Any) -> None:
        with self._lock:
            if key not in self._data and len(self._data) >= self.max_entries:
                self._data.pop(next(iter(self._data)))
                self.stats.evictions += 1
            self._data[key] = (value, time.time() + self.ttl_s)

    def get_or_compute(self, key: Any, compute) -> tuple[Any, bool]:
        cached = self.get(key)
        if cached is not None:
            return cached, True
        value = compute()
        self.put(key, value)
        return value, False

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def stats_dict(self) -> dict[str, Any]:
        total = self.stats.hits + self.stats.misses
        return {
            "entries": len(self._data),
            "hits": self.stats.hits,
            "misses": self.stats.misses,
            "evictions": self.stats.evictions,
            "hit_rate": round(self.stats.hits / total, 3) if total else 0.0,
            "hit_latency_us": round(self.stats.hit_latency_us, 3),
        }


class Prefetcher:
    """Speculative warm-up. A prediction is used only on an exact key match."""

    def __init__(self, cache: HotCache) -> None:
        self.cache = cache
        self.predicted = 0
        self.used = 0

    def predict(self, request: str) -> list[str]:
        words = {word.lower() for word in request.split()}
        goals: list[str] = []
        if words & {"markdown", "report", "summary", "format"}:
            goals.append("markdown")
        if words & {"upper", "uppercase", "shout"}:
            goals.append("upper")
        if words & {"length", "count", "size"}:
            goals.append("length")
        if words & {"reverse", "backwards"}:
            goals.append("reversed")
        return goals

    def prefetch(self, request: str) -> int:
        warmed = 0
        for goal in [request] + [f"{request} {name}" for name in self.predict(request)]:
            key = ("embed", goal)
            if self.cache.get(key) is None:
                self.cache.put(key, embed(goal))
                warmed += 1
        self.predicted += warmed
        return warmed

    def embedding(self, text: str) -> tuple[Any, bool]:
        key = ("embed", text)
        cached = self.cache.get(key)
        if cached is not None:
            self.used += 1
            return cached, True
        value = embed(text)
        self.cache.put(key, value)
        return value, False

    def stats_dict(self) -> dict[str, Any]:
        return {"predicted": self.predicted, "used": self.used}


class RemoteExecutor:
    """Optional remote compute. Refuses when no endpoint is configured."""

    def __init__(self, endpoint=None, token=None, post=None, timeout: float = 30.0) -> None:
        self.endpoint = endpoint or os.environ.get("SOVEREIGN_REMOTE_EXECUTOR", "")
        self.token = token or os.environ.get("SOVEREIGN_REMOTE_TOKEN", "")
        self.timeout = timeout
        self._post = post or self._http_post

    @property
    def available(self) -> bool:
        return bool(self.endpoint)

    def _http_post(self, url, headers, payload):
        import httpx

        response = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def submit(self, capability: str, payloads: list[Any]) -> dict[str, Any]:
        if not self.available:
            raise RemoteUnavailable(
                "no remote executor configured; set SOVEREIGN_REMOTE_EXECUTOR"
            )
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        return self._post(
            self.endpoint, headers, {"capability": capability, "payloads": payloads}
        )


_CPU_SOURCE = """def run(payload):
    total = 0
    for i in range(int(payload.get("n", 1000))):
        total += i * i
    return {"value": total}
"""


def benchmark(
    n: int = 100000,
    capability: str = "text.tokenize",
    mode: str = "processes",
    workers: int | None = None,
    workload: str = "tokenize",
    iterations: int = 20000,
) -> dict[str, Any]:
    if workload == "cpu":
        kind, ref = "source", _CPU_SOURCE
        payload = {"n": iterations}
        name = "cpu.square_sum"
    elif workload == "tokenize":
        if capability not in NATIVE:
            raise ExecutionError(f"unknown native capability: {capability}")
        kind, ref = "native", capability
        payload = {"value": "the quick brown fox jumps over the lazy dog"}
        name = capability
    else:
        raise ExecutionError(f"unknown workload: {workload}")
    result = ExecutionEngine().run_batch(
        kind, ref, [payload] * n, mode=mode, workers=workers, baseline=True
    )
    body = result.to_dict()
    body["workload"] = workload
    body["capability"] = name
    return body
