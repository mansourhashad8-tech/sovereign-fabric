from sovereign.capabilities import CapabilityRegistry, bootstrap_native
from sovereign.properties import check_capabilities
from sovereign.store import FabricStore


def test_native_capabilities_satisfy_their_invariants():
    store = FabricStore()
    registry = CapabilityRegistry(store)
    bootstrap_native(registry)
    result = check_capabilities(registry, cases=20)
    assert result["passed"] is True
    assert len(result["capabilities"]) == 5
    store.close()


def test_a_broken_implementation_is_caught():
    store = FabricStore()
    registry = CapabilityRegistry(store)
    bootstrap_native(registry)

    class Broken:
        def invoke(self, name, payload):
            if name == "tokens.count":
                return {"value": {"wrong": 99}}
            return registry.invoke(name, payload)

    result = check_capabilities(Broken(), cases=5)
    assert result["passed"] is False
    failed = [item for item in result["capabilities"] if item["failed"]]
    assert failed and failed[0]["name"] == "tokens.count"
    store.close()
