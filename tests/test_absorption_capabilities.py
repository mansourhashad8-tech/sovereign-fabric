import os

import pytest

from sovereign.absorption import absorb, propose_capabilities
from sovereign.capabilities import CapabilityError, CapabilityRegistry, bootstrap_native
from sovereign.models import Capability, KnowledgeUnit, Provenance
from sovereign.store import FabricStore


def _unit(uid, title, source="local", tags=("algorithm",), concepts=("planning",)):
    return KnowledgeUnit(
        id=uid,
        title=title,
        summary="summary text",
        provenance=Provenance(source=source, url=f"local://{uid}"),
        concepts=concepts,
        tags=tags,
    )


def test_absorb_indexes_and_links():
    store = FabricStore()
    count = absorb(store, [_unit("u1", "Planner"), _unit("u2", "Search")])
    assert count == 2
    assert store.count_knowledge() == 2
    edges = store.neighbors("u1")
    assert ("u1", "has_concept", "planning") in edges
    assert ("u1", "from_source", "local") in edges
    concept_edges = store.neighbors("planning")
    assert ("planning", "supported_by", "local") in concept_edges
    assert store.list_events("absorption")
    store.close()


def test_propose_capabilities_only_for_executable_units():
    units = [
        _unit("p", "planner", source="pypi", tags=("package", "pypi")),
        _unit("d", "paper", source="arxiv", tags=("paper",)),
    ]
    proposals = propose_capabilities(units)
    assert len(proposals) == 1
    assert proposals[0]["name"] == "use.planner"


def test_bootstrap_registers_native_chain():
    store = FabricStore()
    registry = CapabilityRegistry(store)
    bootstrap_native(registry)
    bootstrap_native(registry)  # idempotent
    names = {c.name for c in registry.list_active()}
    assert {"text.tokenize", "tokens.count", "counts.summarize", "report.format"} <= names
    assert len([c for c in store.list_capabilities() if c.name == "text.tokenize"]) == 1
    store.close()


def test_invoke_builtin_chain():
    store = FabricStore()
    registry = CapabilityRegistry(store)
    bootstrap_native(registry)
    tokens = registry.invoke("text.tokenize", {"value": "a b a"})
    assert tokens == {"value": ["a", "b", "a"]}
    counts = registry.invoke("tokens.count", tokens)
    assert counts == {"value": {"a": 2, "b": 1}}
    report = registry.invoke("counts.summarize", counts)
    assert report["value"]["distinct"] == 2
    assert report["value"]["top"][0] == ["a", 2]
    store.close()


def test_invoke_missing_capability_raises():
    store = FabricStore()
    registry = CapabilityRegistry(store)
    with pytest.raises(CapabilityError):
        registry.invoke("does.not.exist", {})
    store.close()


def test_versioning_and_rollback():
    store = FabricStore()
    registry = CapabilityRegistry(store)
    base = dict(name="x.op", description="d", inputs=("a",), outputs=("b",))
    v1 = registry.register(Capability(**base))
    v2 = registry.register(Capability(**base))
    assert (v1.version, v2.version) == (1, 2)
    assert registry.active("x.op").version == 2
    previous = registry.rollback("x.op")
    assert previous is not None and previous.version == 1
    assert registry.get("x.op", 2).status == "rolled_back"
    store.close()


def test_quarantine_is_not_active():
    store = FabricStore()
    registry = CapabilityRegistry(store)
    registry.register(
        Capability(name="q.op", description="d", inputs=("a",), outputs=("b",)),
        activate=False,
    )
    assert registry.active("q.op") is None
    assert registry.get("q.op").status == "quarantined"
    store.close()


def test_sandboxed_invocation_runs_generated_code():
    store = FabricStore()
    registry = CapabilityRegistry(store)
    source = 'def run(payload):\n    return {"value": str(payload.get("value", "")).upper()}\n'
    registry.register(
        Capability(
            name="text.upper",
            description="uppercase",
            inputs=("text",),
            outputs=("upper",),
            kind="synthesized",
            entry=source,
        )
    )
    assert registry.invoke("text.upper", {"value": "abc"}) == {"value": "ABC"}
    store.close()


def test_sandboxed_failure_becomes_capability_error():
    store = FabricStore()
    registry = CapabilityRegistry(store)
    source = 'def run(payload):\n    raise ValueError("boom")\n'
    registry.register(
        Capability(
            name="bad.op",
            description="bad",
            inputs=("a",),
            outputs=("b",),
            kind="synthesized",
            entry=source,
        )
    )
    with pytest.raises(CapabilityError):
        registry.invoke("bad.op", {"value": "x"})
    store.close()


def test_sandbox_strips_secret_environment():
    os.environ["SOVEREIGN_TEST_TOKEN"] = "super-secret"
    try:
        store = FabricStore()
        registry = CapabilityRegistry(store)
        source = (
            "import os\n"
            "def run(payload):\n"
            '    return {"value": os.environ.get("SOVEREIGN_TEST_TOKEN")}\n'
        )
        registry.register(
            Capability(
                name="env.probe",
                description="probe",
                inputs=("a",),
                outputs=("b",),
                kind="synthesized",
                entry=source,
            )
        )
        assert registry.invoke("env.probe", {}) == {"value": None}
        store.close()
    finally:
        del os.environ["SOVEREIGN_TEST_TOKEN"]
