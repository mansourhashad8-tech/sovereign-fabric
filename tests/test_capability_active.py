from sovereign.capabilities import CapabilityRegistry
from sovereign.evolution import EvolutionEngine
from sovereign.store import FabricStore


def test_list_active_returns_only_the_highest_admitted_version():
    engine = EvolutionEngine(FabricStore(), experts=[])
    registry = engine.registry
    current = registry.active("tokens.count")
    assert current is not None
    registry.register(
        type(current)(
            name=current.name,
            description=current.description,
            inputs=current.inputs,
            outputs=current.outputs,
            kind=current.kind,
            entry=current.entry,
            provenance=current.provenance,
        ),
        version=current.version + 1,
        activate=True,
    )
    active = registry.list_active()
    names = [cap.name for cap in active]
    assert names.count("tokens.count") == 1
    assert registry.active("tokens.count").version == current.version + 1
