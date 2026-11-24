import time

from sovereign.capabilities import CapabilityRegistry, bootstrap_native
from sovereign.evolution import EvolutionEngine
from sovereign.guardians import GuardianRegistry, LocalGuardian
from sovereign.loop import EvolutionLoop
from sovereign.optimizer import Optimizer
from sovereign.store import FabricStore


def _engine():
    store = FabricStore()
    registry = CapabilityRegistry(store)
    bootstrap_native(registry)
    guardians = GuardianRegistry([LocalGuardian()])
    return store, EvolutionEngine(store, guardians=guardians)


def test_tick_absorbs_and_records_a_generation():
    store, engine = _engine()
    loop = EvolutionLoop(engine, sources=["local"], optimize=False)
    summary = loop.tick()
    assert summary["generation"] == 1
    assert summary["sources"]["local"] == "ok"
    assert loop.status()["generation"] == 1
    assert store.list_events("loop.tick")
    store.close()


def test_tick_can_run_a_measured_optimization():
    store, engine = _engine()
    loop = EvolutionLoop(engine, sources=["local"], optimize=True)
    summary = loop.tick()
    assert summary["optimization"] is not None
    assert "variants" in summary["optimization"]
    store.close()


def test_start_and_stop_are_real():
    store, engine = _engine()
    loop = EvolutionLoop(engine, interval_s=0.05, sources=["local"], optimize=False)
    loop.start()
    time.sleep(0.2)
    status = loop.stop()
    assert status["generation"] >= 1
    assert status["running"] is False
    store.close()


def test_optimizer_uses_the_same_registry():
    store, engine = _engine()
    optimizer = Optimizer(engine.registry)
    result = optimizer.optimize("tokens.count", repeats=2)
    assert result["name"] == "tokens.count"
    assert any(item["verified"] for item in result["variants"])
    store.close()
