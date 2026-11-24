import pytest

from sovereign.execution import (
    ExecutionEngine,
    ExecutionError,
    HotCache,
    Prefetcher,
    RemoteExecutor,
    RemoteUnavailable,
    benchmark,
)


def _payloads(n=40):
    return [{"value": f"alpha beta {i}"} for i in range(n)]


def test_serial_threads_processes_agree():
    engine = ExecutionEngine()
    payloads = _payloads()
    serial = engine.run_batch("native", "text.tokenize", payloads, mode="serial")
    threads = engine.run_batch("native", "text.tokenize", payloads, mode="threads", workers=2)
    processes = engine.run_batch(
        "native", "text.tokenize", payloads, mode="processes", workers=2
    )
    assert serial.sample == threads.sample == processes.sample
    assert processes.count == len(payloads)
    assert processes.sample[0] == {"value": ["alpha", "beta", "0"]}


def test_speedup_is_measured_not_invented():
    engine = ExecutionEngine()
    result = engine.run_batch("native", "text.tokenize", _payloads(200), mode="processes")
    assert result.serial_duration_s > 0
    assert result.duration_s > 0
    assert result.speedup == pytest.approx(
        result.serial_duration_s / result.duration_s, rel=1e-6
    )
    assert "measured" in result.note or "no parallel gain" in result.note


def test_empty_batch_is_safe():
    result = ExecutionEngine().run_batch("native", "text.tokenize", [], mode="auto")
    assert result.count == 0
    assert result.speedup == 0.0


def test_unknown_mode_rejected():
    with pytest.raises(ExecutionError):
        ExecutionEngine().run_batch("native", "text.tokenize", _payloads(2), mode="quantum")


def test_cache_hit_is_fast_and_counted():
    cache = HotCache()
    cache.put("k", {"value": 1})
    assert cache.get("k") == {"value": 1}
    assert cache.get("k") == {"value": 1}
    stats = cache.stats_dict()
    assert stats["hits"] == 2
    assert stats["hit_latency_us"] > 0


def test_get_or_compute_runs_once():
    cache = HotCache()
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return 42

    assert cache.get_or_compute("x", compute) == (42, False)
    assert cache.get_or_compute("x", compute) == (42, True)
    assert calls["n"] == 1


def test_cache_expires():
    cache = HotCache(ttl_s=-1)
    cache.put("k", 1)
    assert cache.get("k") is None


def test_prefetch_is_used_only_on_exact_match():
    cache = HotCache()
    prefetcher = Prefetcher(cache)
    warmed = prefetcher.prefetch("markdown report about planning")
    assert warmed > 0
    vector, hit = prefetcher.embedding("markdown report about planning")
    assert hit is True
    _, miss = prefetcher.embedding("a completely different query")
    assert miss is False
    assert prefetcher.stats_dict()["used"] >= 1


def test_remote_executor_refuses_without_endpoint():
    remote = RemoteExecutor(endpoint="")
    assert remote.available is False
    with pytest.raises(RemoteUnavailable):
        remote.submit("text.tokenize", [{"value": "a"}])


def test_remote_executor_uses_configured_endpoint():
    captured = {}

    def fake_post(url, headers, payload):
        captured["url"] = url
        return {"ok": True, "count": len(payload["payloads"])}

    remote = RemoteExecutor(endpoint="https://hpc.example/run", post=fake_post)
    assert remote.available is True
    body = remote.submit("text.tokenize", [{"value": "a"}])
    assert body == {"ok": True, "count": 1}
    assert captured["url"] == "https://hpc.example/run"


def test_benchmark_returns_measured_fields():
    body = benchmark(n=50, mode="serial")
    assert body["count"] == 50
    assert body["duration_s"] > 0
    assert body["throughput_per_s"] > 0
    assert body["speedup"] >= 0


def test_serial_mode_does_not_fake_a_speedup():
    result = ExecutionEngine().run_batch(
        "native", "text.tokenize", _payloads(50), mode="serial"
    )
    assert result.speedup == pytest.approx(1.0, abs=1e-9)
    assert result.duration_s == result.serial_duration_s


def test_cpu_workload_benchmark():
    body = benchmark(n=8, mode="serial", workload="cpu", iterations=1000)
    assert body["count"] == 8
    assert body["sample"][0] == {"value": 332833500}
