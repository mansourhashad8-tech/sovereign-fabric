"""In-process hyper kernel: superposition memory, state bus, observer, clock.

This is a classical, dependency-free implementation of four internal
mechanisms. The memory is a holographic reduced representation (HRR): bindings
are circular convolutions and the memory is their superposition. It is
"quantum-inspired" mathematics, not quantum hardware and not an exponential
speedup. The bus transfers Python object references inside one process; it does
not serialize and it is not a network protocol. The clock uses
``time.perf_counter_ns``; its resolution is measured, not assumed to be
picoseconds.
"""

from __future__ import annotations

import cmath
import hashlib
import math
import threading
import time
from collections import Counter, defaultdict, deque
from typing import Any, Callable

from .vectors import embed

_MAX_MEMORY_ITEMS = 10_000
_MAX_BUS_ITEMS = 2_000


def _fft(values: list[complex]) -> list[complex]:
    size = len(values)
    if size == 1:
        return list(values)
    even = _fft(values[0::2])
    odd = _fft(values[1::2])
    result = [0j] * size
    for index in range(size // 2):
        factor = cmath.exp(-2j * math.pi * index / size) * odd[index]
        result[index] = even[index] + factor
        result[index + size // 2] = even[index] - factor
    return result


def _ifft(values: list[complex]) -> list[complex]:
    size = len(values)
    conjugated = [value.conjugate() for value in values]
    transformed = _fft(conjugated)
    return [value.conjugate() / size for value in transformed]


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values] if norm else values


def _encode(text: str, dim: int) -> list[float]:
    vector = embed(text, dim)
    if any(vector):
        return vector
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=32).digest()
    fallback = [0.0] * dim
    for index, byte in enumerate(digest):
        fallback[index % dim] += 1.0 if byte & 1 else -1.0
    return _normalize(fallback)


def _bind(left: list[float], right: list[float]) -> list[float]:
    left_f = _fft([complex(value) for value in left])
    right_f = _fft([complex(value) for value in right])
    product = [a * b for a, b in zip(left_f, right_f)]
    return _normalize([value.real for value in _ifft(product)])


def _unbind(memory: list[float], key: list[float]) -> list[float]:
    memory_f = _fft([complex(value) for value in memory])
    key_f = _fft([complex(value) for value in key])
    product = [a * b.conjugate() for a, b in zip(memory_f, key_f)]
    return _normalize([value.real for value in _ifft(product)])


class HolographicMemory:
    def __init__(self, dim: int = 128) -> None:
        if dim < 8 or dim & (dim - 1):
            raise ValueError("dim must be a power of two and at least 8")
        self.dim = dim
        self._memory = [0.0] * dim
        self._values: list[tuple[str, str, list[float], list[float]]] = []
        self._lock = threading.RLock()

    def remember(self, key: str, value: str) -> int:
        with self._lock:
            if len(self._values) >= _MAX_MEMORY_ITEMS:
                raise ValueError("memory capacity reached")
            if not key.strip() or not value.strip():
                raise ValueError("key and value must not be empty")
            key_vector = _encode(key, self.dim)
            value_vector = _encode(value, self.dim)
            binding = _bind(key_vector, value_vector)
            self._memory = [a + b for a, b in zip(self._memory, binding)]
            self._values.append((key, value, key_vector, value_vector))
            return len(self._values)

    def recall(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        k = max(1, min(int(k), 20))
        with self._lock:
            if not self._values:
                return []
            if not query.strip():
                return []
            key_vector = _encode(query, self.dim)
            probe = _unbind(self._memory, key_vector)
            ranked = [
                (value, sum(a * b for a, b in zip(probe, value_vector)))
                for _, value, _, value_vector in self._values
            ]
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return [{"value": value, "score": round(score, 6)} for value, score in ranked[:k]]

    def repair(self) -> bool:
        with self._lock:
            if len(self._memory) == self.dim and all(
                math.isfinite(value) for value in self._memory
            ):
                return False
            rebuilt = [0.0] * self.dim
            for key, _, key_vector, value_vector in self._values:
                binding = _bind(key_vector, value_vector)
                rebuilt = [a + b for a, b in zip(rebuilt, binding)]
            self._memory = rebuilt
            return True

    def clear(self) -> None:
        with self._lock:
            self._memory = [0.0] * self.dim
            self._values.clear()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "dim": self.dim,
                "items": len(self._values),
                "capacity": _MAX_MEMORY_ITEMS,
                "memory_norm": round(math.sqrt(sum(v * v for v in self._memory)), 6),
                "approximate_bytes": 8 * self.dim
                + sum(
                    16 * self.dim
                    + len(key.encode("utf-8"))
                    + len(value.encode("utf-8"))
                    for key, value, _, _ in self._values
                ),
                "kind": "classical HRR superposition, not quantum hardware",
            }


class StateBus:
    def __init__(self) -> None:
        self._state: dict[str, Any] = {}
        self._subscribers: dict[str, list[Callable[[Any], None]]] = defaultdict(list)
        self._lock = threading.RLock()
        self._sequence = 0
        self._deliveries = 0

    def put(self, key: str, value: Any) -> int:
        with self._lock:
            if key not in self._state and len(self._state) >= _MAX_BUS_ITEMS:
                raise ValueError("state bus capacity reached")
            self._state[key] = value
            self._sequence += 1
            sequence = self._sequence
            subscribers = list(self._subscribers.get(key, ()))
        for callback in subscribers:
            callback(value)
            self._deliveries += 1
        return sequence

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._state.get(key, default)

    def subscribe(self, key: str, callback: Callable[[Any], None]) -> None:
        with self._lock:
            self._subscribers[key].append(callback)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "items": len(self._state),
                "capacity": _MAX_BUS_ITEMS,
                "sequence": self._sequence,
                "deliveries": self._deliveries,
                "subscribers": sum(len(items) for items in self._subscribers.values()),
                "serialization": False,
                "transport": "in-process object references",
            }


class InnerObserver:
    def __init__(self, window: int = 256, threshold: float = 4.0) -> None:
        self.window = max(8, int(window))
        self.threshold = max(1.0, float(threshold))
        self._samples: deque[tuple[str, int, bool]] = deque(maxlen=self.window)
        self._sum_ns = 0.0
        self._sum_sq_ns = 0.0
        self._healers: dict[str, Callable[[dict[str, Any]], bool]] = {}
        self._lock = threading.RLock()
        self.total = 0
        self.errors = 0
        self.anomalies = 0
        self.healed = 0

    def register_healer(self, component: str, callback: Callable[[dict[str, Any]], bool]) -> None:
        with self._lock:
            self._healers[component] = callback

    def observe(self, component: str, duration_ns: int, ok: bool = True) -> bool:
        with self._lock:
            if len(self._samples) == self.window:
                _, old_ns, _ = self._samples[0]
                self._sum_ns -= old_ns
                self._sum_sq_ns -= old_ns * old_ns
            sample_count = len(self._samples)
            mean = self._sum_ns / sample_count if sample_count else 0.0
            variance = (
                max(0.0, self._sum_sq_ns / sample_count - mean * mean)
                if sample_count
                else 0.0
            )
            deviation = math.sqrt(variance)
            anomaly = (not ok) or (
                sample_count >= 8
                and duration_ns > mean + self.threshold * deviation
                and duration_ns > 1_000
            )
            self._samples.append((component, int(duration_ns), bool(ok)))
            self._sum_ns += int(duration_ns)
            self._sum_sq_ns += int(duration_ns) * int(duration_ns)
            self.total += 1
            if not ok:
                self.errors += 1
            if anomaly:
                self.anomalies += 1
            healer = self._healers.get(component)
        if anomaly and healer is not None:
            snapshot = self.snapshot()
            try:
                repaired = bool(healer(snapshot))
            except Exception:
                repaired = False
            if repaired:
                with self._lock:
                    self.healed += 1
        return anomaly

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            values = sorted(sample[1] for sample in self._samples)
            total = self.total
            errors = self.errors
            anomalies = self.anomalies
            healed = self.healed
            by_component = Counter(sample[0] for sample in self._samples)
        def percentile(fraction: float) -> int:
            if not values:
                return 0
            return values[min(len(values) - 1, int(fraction * len(values)))]
        error_rate = errors / total if total else 0.0
        anomaly_rate = anomalies / total if total else 0.0
        return {
            "samples": len(values),
            "total": total,
            "errors": errors,
            "anomalies": anomalies,
            "healed": healed,
            "error_rate": round(error_rate, 6),
            "anomaly_rate": round(anomaly_rate, 6),
            "p50_ns": percentile(0.50),
            "p95_ns": percentile(0.95),
            "max_ns": values[-1] if values else 0,
            "components": dict(by_component),
            "health": "degraded" if error_rate > 0.01 or anomaly_rate > 0.05 else "ok",
            "overhead": "synchronous O(1) rolling mean/variance; not zero",
        }


class InternalClock:
    def __init__(self) -> None:
        self._epoch = time.perf_counter_ns()
        self._sequence = 0
        self._lock = threading.RLock()

    def tick(self) -> dict[str, int]:
        with self._lock:
            self._sequence += 1
            return {
                "sequence": self._sequence,
                "ns_since_epoch": time.perf_counter_ns() - self._epoch,
            }

    def now_ns(self) -> int:
        return time.perf_counter_ns()

    def resolution_ns(self, samples: int = 1000) -> int:
        samples = max(10, min(int(samples), 10_000))
        previous = time.perf_counter_ns()
        best = None
        for _ in range(samples):
            current = time.perf_counter_ns()
            delta = current - previous
            if delta > 0 and (best is None or delta < best):
                best = delta
            previous = current
        return best or 0

    def barrier(self, participants: int, timeout_s: float = 2.0) -> dict[str, Any]:
        participants = max(2, min(int(participants), 32))
        barrier = threading.Barrier(participants)
        stamps: list[int] = []
        lock = threading.Lock()

        def worker() -> None:
            barrier.wait(timeout=timeout_s)
            stamp = time.perf_counter_ns()
            with lock:
                stamps.append(stamp)

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(participants)]
        started = time.perf_counter_ns()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=timeout_s)
        elapsed = time.perf_counter_ns() - started
        return {
            "participants": participants,
            "arrived": len(stamps),
            "elapsed_ns": elapsed,
            "skew_ns": max(stamps) - min(stamps) if stamps else 0,
            "precision": "measured perf_counter_ns, not picoseconds",
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "epoch_ns": self._epoch,
                "sequence": self._sequence,
                "resolution_ns": self.resolution_ns(100),
                "precision": "measured perf_counter_ns, not picoseconds",
            }


class HyperKernel:
    def __init__(self) -> None:
        self.memory = HolographicMemory()
        self.bus = StateBus()
        self.observer = InnerObserver()
        self.clock = InternalClock()
        self.observer.register_healer("memory", lambda _: self.memory.repair())

    def status(self) -> dict[str, Any]:
        return {
            "memory": self.memory.status(),
            "bus": self.bus.stats(),
            "observer": self.observer.snapshot(),
            "clock": self.clock.status(),
            "limits": {
                "quantum_hardware": False,
                "near_light_signaling": False,
                "picosecond_precision": False,
                "note": "classical in-process mechanisms with measured bounds",
            },
        }

    def benchmark(self, iterations: int = 100) -> dict[str, Any]:
        iterations = max(5, min(int(iterations), 500))
        bus = StateBus()
        memory = HolographicMemory()
        observer = InnerObserver()
        clock = InternalClock()
        bus_ns: list[int] = []
        memory_ns: list[int] = []
        observer_ns: list[int] = []
        clock_ns: list[int] = []
        payload = {"task": "benchmark", "state": list(range(8))}
        for index in range(iterations):
            started = time.perf_counter_ns()
            bus.put(f"k{index}", payload)
            bus.get(f"k{index}")
            bus_ns.append(time.perf_counter_ns() - started)

            started = time.perf_counter_ns()
            memory.remember(f"key {index}", f"value {index}")
            memory.recall(f"key {index}", k=1)
            memory_ns.append(time.perf_counter_ns() - started)

            started = time.perf_counter_ns()
            observer.observe("benchmark", 1000)
            observer_ns.append(time.perf_counter_ns() - started)

            started = time.perf_counter_ns()
            clock.tick()
            clock_ns.append(time.perf_counter_ns() - started)
        return {
            "iterations": iterations,
            "bus_put_get_ns": _summarize(bus_ns),
            "memory_remember_recall_ns": _summarize(memory_ns),
            "observer_observe_ns": _summarize(observer_ns),
            "clock_tick_ns": _summarize(clock_ns),
            "clock_resolution_ns": clock.resolution_ns(200),
            "memory_items": memory.status()["items"],
            "note": "wall-clock measurements in this process; no external service",
        }


def _summarize(values: list[int]) -> dict[str, int]:
    ordered = sorted(values)
    def at(fraction: float) -> int:
        return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]
    return {
        "p50": at(0.50),
        "p95": at(0.95),
        "max": ordered[-1],
        "mean": int(sum(ordered) / len(ordered)),
    }
