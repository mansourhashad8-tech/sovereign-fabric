from sovereign.programs import ProgramSearch


def test_finds_each_supported_shape():
    cases = [
        ([({"value": "Hello World"}, {"value": "hello-world"})], "slug"),
        ([({"value": "hello world"}, {"value": "Hello World"})], "title case"),
        ([({"value": "one two"}, {"value": "two one"})], "words reversed"),
        ([({"value": [1, 2, 3]}, {"value": 6})], "sum"),
        ([({"value": "Ada Lovelace"}, {"value": "AL"})], "initials"),
    ]
    for pairs, label in cases:
        found = ProgramSearch().find(pairs)
        assert found is not None, label
        assert found[1] == label


def test_returns_none_when_nothing_fits():
    assert ProgramSearch().find([({"value": "abc"}, {"value": "zzz"})]) is None


def test_generated_program_passes_the_gate():
    from sovereign.capabilities import CapabilityRegistry, bootstrap_native
    from sovereign.store import FabricStore
    from sovereign.synthesis import Synthesizer

    store = FabricStore()
    registry = CapabilityRegistry(store)
    bootstrap_native(registry)
    synth = Synthesizer(registry)
    pairs = [
        ({"value": "Hello World"}, {"value": "hello-world"}),
        ({"value": "A B"}, {"value": "a-b"}),
    ]
    source, _ = ProgramSearch().find(pairs)
    result = synth.verify(source, pairs)
    assert result.admitted is True
    assert result.passed == 2
    store.close()
