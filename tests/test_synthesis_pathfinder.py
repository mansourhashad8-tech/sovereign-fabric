from sovereign.capabilities import CapabilityRegistry
from sovereign.models import Capability
from sovereign.pathfinder import Operator, PathFinder, operators_from
from sovereign.store import FabricStore
from sovereign.synthesis import Synthesizer

UPPER_EXAMPLES = [({"value": "abc"}, {"value": "ABC"}), ({"value": "z9"}, {"value": "Z9"})]


def _registry():
    store = FabricStore()
    return CapabilityRegistry(store), store


def test_verify_passes_on_correct_implementation():
    registry, store = _registry()
    synth = Synthesizer(registry)
    result = synth.verify('def run(payload):\n    return {"value": str(payload.get("value","")).upper()}\n', UPPER_EXAMPLES)
    assert result.admitted is True
    assert result.passed == 2 and result.failed == 0
    store.close()


def test_verify_rejects_wrong_implementation():
    registry, store = _registry()
    synth = Synthesizer(registry)
    result = synth.verify('def run(payload):\n    return {"value": payload.get("value","")}\n', UPPER_EXAMPLES)
    assert result.admitted is False
    assert result.failed == 2
    assert result.failures
    store.close()


def test_verify_requires_examples():
    registry, store = _registry()
    synth = Synthesizer(registry)
    assert synth.verify("def run(p):\n    return p\n", []).admitted is False
    store.close()


def test_synthesize_admits_and_registers_capability():
    registry, store = _registry()
    synth = Synthesizer(registry)
    result = synth.synthesize(
        name="text.upper",
        description="uppercase",
        inputs=("text",),
        outputs=("upper",),
        spec={"op": "upper"},
        examples=UPPER_EXAMPLES,
    )
    assert result.admitted is True
    assert result.capability is not None
    assert registry.active("text.upper") is not None
    assert registry.invoke("text.upper", {"value": "ab"}) == {"value": "AB"}
    store.close()


def test_synthesize_rejection_is_quarantined():
    registry, store = _registry()
    synth = Synthesizer(registry)
    result = synth.synthesize(
        name="text.lower",
        description="wrong op for upper examples",
        inputs=("text",),
        outputs=("lower",),
        spec={"op": "lower"},
        examples=UPPER_EXAMPLES,
    )
    assert result.admitted is False
    assert registry.active("text.lower") is None
    assert registry.get("text.lower").status == "quarantined"
    store.close()


def test_unknown_operation_is_rejected():
    registry, store = _registry()
    synth = Synthesizer(registry)
    result = synth.synthesize(
        name="weird.op", description="d", inputs=("a",), outputs=("b",),
        spec={"op": "teleport"}, examples=UPPER_EXAMPLES,
    )
    assert result.admitted is False
    assert "template" in result.reason
    store.close()


def test_synthesis_can_override_with_custom_source():
    registry, store = _registry()
    synth = Synthesizer(registry)
    result = synth.synthesize(
        name="text.double",
        description="double a string",
        inputs=("text",),
        outputs=("doubled",),
        spec={"source": 'def run(payload):\n    v = payload.get("value","")\n    return {"value": v + v}\n'},
        examples=[({"value": "ab"}, {"value": "abab"})],
    )
    assert result.admitted is True
    store.close()


def _chain_ops():
    caps = [
        Capability(name="text.tokenize", description="", inputs=("text",), outputs=("tokens",)),
        Capability(name="tokens.count", description="", inputs=("tokens",), outputs=("counts",)),
        Capability(name="counts.summarize", description="", inputs=("counts",), outputs=("report",)),
        Capability(name="report.format", description="", inputs=("report",), outputs=("markdown",)),
    ]
    return operators_from(caps)


def test_pathfinder_finds_shortest_chain():
    pf = PathFinder()
    plan = pf.plan(("text",), "markdown", _chain_ops())
    assert plan.solved is True
    assert [s.capability for s in plan.steps] == [
        "text.tokenize",
        "tokens.count",
        "counts.summarize",
        "report.format",
    ]
    assert plan.steps[0].produces == ("tokens",)


def test_pathfinder_goal_already_available():
    pf = PathFinder()
    plan = pf.plan(("text", "markdown"), "markdown", _chain_ops())
    assert plan.solved is True and plan.steps == []


def test_pathfinder_unsolvable_is_memoised():
    store = FabricStore()
    pf = PathFinder(store)
    ops = _chain_ops()
    first = pf.plan(("text",), "quantum-state", ops)
    assert first.solved is False
    assert "no applicable route" in first.reason
    assert store.memo_entries()

    second = pf.plan(("text",), "quantum-state", ops)
    assert second.solved is False
    assert "pruned" in second.reason
    store.close()


def test_pathfinder_budget_exhaustion_is_not_memoised():
    store = FabricStore()
    pf = PathFinder(store)
    plan = pf.plan(("text",), "markdown", _chain_ops(), max_expansions=1)
    assert plan.solved is False
    assert "budget" in plan.reason
    assert store.memo_entries() == []
    store.close()


def test_pathfinder_proves_unreachable_without_expanding_or_guessing():
    store = FabricStore()
    pf = PathFinder(store)
    plan = pf.plan(("text",), "unreachable", _chain_ops(), max_expansions=1)
    assert plan.solved is False
    assert plan.explored == 0
    assert "no applicable route" in plan.reason
    assert store.memo_entries()
    store.close()


def test_pathfinder_plan_many_is_parallel_and_complete():
    pf = PathFinder()
    results = pf.plan_many(("text",), ["tokens", "counts", "markdown", "nope"], _chain_ops())
    assert results["tokens"].solved is True
    assert results["counts"].solved is True
    assert results["markdown"].solved is True
    assert results["nope"].solved is False
    assert len(results["markdown"].steps) == 4


def test_operators_from_sorts_deterministically():
    caps = [
        Capability(name="b.op", description="", inputs=("a",), outputs=("b",)),
        Capability(name="a.op", description="", inputs=("a",), outputs=("b",)),
    ]
    ops = operators_from(caps)
    assert [o.name for o in ops] == ["a.op", "b.op"]
    assert isinstance(ops[0], Operator)


def test_alternatives_finds_distinct_routes():
    from sovereign.pathfinder import Operator, PathFinder

    ops = [
        Operator("to_tokens", frozenset({"text"}), frozenset({"tokens"})),
        Operator("tokens_md", frozenset({"tokens"}), frozenset({"markdown"})),
        Operator("direct_md", frozenset({"text"}), frozenset({"markdown"})),
    ]
    alternatives = PathFinder().alternatives(("text",), "markdown", ops, k=3)
    assert len(alternatives) >= 2
    assert [s.capability for s in alternatives[0].steps] == ["direct_md"]
    assert [s.capability for s in alternatives[1].steps] == ["to_tokens", "tokens_md"]
