import threading

from sovereign.hyper import (
    HolographicMemory,
    HyperKernel,
    InnerObserver,
    InternalClock,
    StateBus,
)


def test_state_bus_transfers_the_same_object_without_serialization():
    bus = StateBus()
    payload = {"task": "x", "state": [1, 2, 3]}
    seen = []
    bus.subscribe("task", seen.append)
    sequence = bus.put("task", payload)
    assert sequence == 1
    assert bus.get("task") is payload
    assert seen == [payload]
    assert bus.stats()["serialization"] is False


def test_holographic_memory_recalls_superposed_items():
    memory = HolographicMemory(dim=64)
    pairs = {
        "sqlite": "write ahead logging",
        "planning": "state space search",
        "arabic": "normalization and stemming",
        "retrieval": "bm25 and semantic ranking",
    }
    for key, value in pairs.items():
        memory.remember(key, value)
    for key, value in pairs.items():
        hits = memory.recall(key, k=1)
        assert hits[0]["value"] == value
    assert memory.status()["items"] == 4


def test_holographic_memory_empty_and_oov_are_safe():
    memory = HolographicMemory(dim=32)
    assert memory.recall("anything") == []
    memory.remember("sqlite", "logging")
    assert memory.recall("") == []


def test_observer_detects_errors_and_calls_a_healer():
    observer = InnerObserver()
    calls = []
    observer.register_healer("db", lambda snapshot: calls.append(snapshot) or True)
    assert observer.observe("db", 1000, ok=True) is False
    assert observer.observe("db", 1000, ok=False) is True
    snapshot = observer.snapshot()
    assert snapshot["errors"] == 1
    assert snapshot["anomalies"] == 1
    assert snapshot["healed"] == 1
    assert calls and calls[0]["errors"] == 1


def test_clock_ticks_and_barrier_arrives():
    clock = InternalClock()
    first = clock.tick()
    second = clock.tick()
    assert second["sequence"] == first["sequence"] + 1
    assert clock.resolution_ns(50) > 0
    result = clock.barrier(2)
    assert result["arrived"] == 2
    assert result["skew_ns"] >= 0


def test_hyper_kernel_benchmark_reports_measurements():
    kernel = HyperKernel()
    report = kernel.benchmark(5)
    assert report["iterations"] == 5
    assert report["bus_put_get_ns"]["p50"] > 0
    assert report["memory_remember_recall_ns"]["p50"] > 0
    assert report["observer_observe_ns"]["p50"] > 0
    assert report["clock_tick_ns"]["p50"] > 0
    assert report["clock_resolution_ns"] > 0
    assert kernel.status()["limits"]["quantum_hardware"] is False


def test_kernel_repairs_a_corrupted_superposition():
    kernel = HyperKernel()
    kernel.memory.remember("sqlite", "write ahead logging")
    kernel.memory.remember("planning", "state space search")
    kernel.memory._memory[0] = float("nan")
    assert kernel.observer.observe("memory", 0, ok=False) is True
    snapshot = kernel.observer.snapshot()
    assert snapshot["healed"] == 1
    assert kernel.memory.status()["memory_norm"] > 0
    assert kernel.memory.recall("sqlite", k=1)[0]["value"] == "write ahead logging"


def test_zero_embedding_text_uses_a_deterministic_fallback():
    memory = HolographicMemory(dim=128)
    memory.remember("value 21", "key 21")
    assert memory.recall("value 21", k=1)[0]["value"] == "key 21"
