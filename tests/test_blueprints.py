from sovereign.blueprints import BLUEPRINTS, Bprint, autonomous_extend
from sovereign.capabilities import CapabilityRegistry, bootstrap_native
from sovereign.pathfinder import PathFinder
from sovereign.store import FabricStore
from sovereign.synthesis import Synthesizer


def _engine():
    store = FabricStore()
    registry = CapabilityRegistry(store)
    bootstrap_native(registry)
    synthesizer = Synthesizer(registry)
    pathfinder = PathFinder(store)
    return store, registry, synthesizer, pathfinder


def test_blueprint_library_is_well_formed():
    assert len(BLUEPRINTS) >= 6
    for bp in BLUEPRINTS:
        assert bp.inputs and bp.outputs
        assert bp.examples, f"{bp.name} has no examples"


def test_autonomous_extend_solves_upper_goal():
    store, registry, synth, pf = _engine()
    plan, added, attempts = autonomous_extend(registry, synth, pf, ("text",), "upper")
    assert plan.solved is True
    assert [s.capability for s in plan.steps] == ["text.upper"]
    assert added == ["text.upper"]
    assert attempts[0]["admitted"] is True
    store.close()


def test_autonomous_extend_picks_custom_source_blueprint():
    store, registry, synth, pf = _engine()
    plan, added, _ = autonomous_extend(registry, synth, pf, ("text",), "doubled")
    assert plan.solved is True
    assert added == ["text.double"]
    assert registry.invoke("text.double", {"value": "ab"}) == {"value": "abab"}
    store.close()


def test_autonomous_extend_skips_blueprint_with_unmet_inputs():
    store, registry, synth, pf = _engine()
    bp = Bprint(
        name="numbers.only",
        description="needs numbers",
        inputs=("numbers",),
        outputs=("total",),
        spec={"op": "sum_list"},
        examples=(({"value": [1, 2]}, {"value": 3}),),
    )
    plan, added, attempts = autonomous_extend(
        registry, synth, pf, ("text",), "total", blueprints=[bp]
    )
    assert plan.solved is False
    assert added == []
    assert attempts == []
    store.close()


def test_autonomous_extend_quarantines_a_failing_blueprint():
    store, registry, synth, pf = _engine()
    bad = Bprint(
        name="text.bad",
        description="lies about its output",
        inputs=("text",),
        outputs=("bad",),
        spec={"op": "upper"},
        examples=(({"value": "abc"}, {"value": "WRONG"}),),
    )
    plan, added, attempts = autonomous_extend(
        registry, synth, pf, ("text",), "bad", blueprints=[bad]
    )
    assert plan.solved is False
    assert added == []
    assert attempts[0]["admitted"] is False
    assert registry.get("text.bad").status == "quarantined"
    store.close()


def test_autonomous_extend_builds_a_two_step_bridge():
    store, registry, synth, pf = _engine()
    to_numbers = Bprint(
        name="text.numbers",
        description="parse numbers from text",
        inputs=("text",),
        outputs=("numbers",),
        spec={
            "source": 'def run(payload):\n'
            '    parts = str(payload.get("value", "")).split()\n'
            '    return {"value": [int(p) for p in parts if p]}\n'
        },
        examples=(({"value": "1 2 3"}, {"value": [1, 2, 3]}),),
    )
    total = Bprint(
        name="list.total",
        description="sum numbers",
        inputs=("numbers",),
        outputs=("total",),
        spec={"op": "sum_list"},
        examples=(({"value": [1, 2, 3]}, {"value": 6}),),
    )
    plan, added, attempts = autonomous_extend(
        registry, synth, pf, ("text",), "total", blueprints=[to_numbers, total]
    )
    assert plan.solved is True
    assert added == ["text.numbers", "list.total"]
    assert [s.capability for s in plan.steps] == ["text.numbers", "list.total"]
    assert len(attempts) == 2
    store.close()


def test_every_blueprint_reproduces_its_own_examples():
    store, registry, synth, _ = _engine()
    try:
        for bp in BLUEPRINTS:
            result = synth.verify(synth.source_for(dict(bp.spec)), list(bp.examples))
            assert result.admitted, f"{bp.name}: {result.reason}"
    finally:
        store.close()


def test_autonomous_extend_builds_an_arabic_pipeline():
    store, registry, synth, pf = _engine()
    plan, added, _ = autonomous_extend(registry, synth, pf, ("text",), "arabic")
    assert plan.solved is True
    assert added == ["text.arabic_normalized"]
    assert registry.invoke("text.arabic_normalized", {"value": "أَكْتُبُ"}) == {
        "value": "اكتب"
    }
    store.close()


def test_autonomous_extend_bridges_text_to_list_and_json():
    store, registry, synth, pf = _engine()
    plan, added, _ = autonomous_extend(registry, synth, pf, ("text",), "unique")
    assert plan.solved is True
    assert added == ["text.tokens", "list.unique"]
    assert registry.invoke("list.unique", {"value": [1, 2, 1]}) == {"value": [1, 2]}
    store.close()

    store, registry, synth, pf = _engine()
    plan, added, _ = autonomous_extend(registry, synth, pf, ("text",), "flat")
    assert plan.solved is True
    assert added == ["text.json", "json.flatten"]
    assert registry.invoke("json.flatten", {"value": {"a": {"b": 1}}}) == {
        "value": {"a.b": 1}
    }
    store.close()
