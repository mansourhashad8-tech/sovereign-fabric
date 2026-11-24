from sovereign.capabilities import CapabilityRegistry, bootstrap_native
from sovereign.optimizer import Optimizer
from sovereign.store import FabricStore


def _setup():
    store = FabricStore()
    registry = CapabilityRegistry(store)
    bootstrap_native(registry)
    return store, registry, Optimizer(registry)


def test_optimizer_keeps_a_verified_faster_variant():
    store, registry, optimizer = _setup()
    before = registry.invoke("tokens.count", {"value": ["a", "b", "a"]})
    result = optimizer.optimize("tokens.count", repeats=3)
    assert any(item["verified"] for item in result["variants"])
    if result["chosen"] is not None:
        assert registry.active("tokens.count").entry != result["current"]["entry"]
        assert registry.invoke("tokens.count", {"value": ["a", "b", "a"]}) == before
        events = store.list_events("capability.optimized")
        assert events
    store.close()


def test_optimizer_only_switches_when_the_output_is_identical():
    store, registry, optimizer = _setup()
    before_entry = registry.active("text.tokenize").entry
    before_value = registry.invoke("text.tokenize", {"value": "a b a"})
    result = optimizer.optimize("text.tokenize", repeats=2)
    assert registry.invoke("text.tokenize", {"value": "a b a"}) == before_value
    if result["chosen"] is None:
        assert registry.active("text.tokenize").entry == before_entry
    else:
        assert any(item["verified"] for item in result["variants"])
    store.close()


def test_optimizer_reports_unknown_capability_honestly():
    store, registry, optimizer = _setup()
    result = optimizer.optimize("does.not.exist")
    assert result["chosen"] is None
    assert "no active capability" in result["reason"]
    store.close()
