import json

import pytest

from sovereign.capabilities import CapabilityError
from sovereign.evolution import EvolutionEngine
from sovereign.store import FabricStore
from sovereign.toolbox import TOOLBOX


CASES = [
    ("hash.sha512", {"value": "abc"}, lambda v: v.startswith("ddaf35")),
    ("hex.encode", {"value": "hi"}, lambda v: v == "6869"),
    ("hex.decode", {"value": "6869"}, lambda v: v == "hi"),
    ("url.encode", {"value": "a b&"}, lambda v: v == "a%20b%26"),
    ("url.decode", {"value": "a%20b%26"}, lambda v: v == "a b&"),
    ("base32.encode", {"value": "hi"}, lambda v: v == "NBUQ===="),
    ("base32.decode", {"value": "NBUQ===="}, lambda v: v == "hi"),
    ("json.flatten", {"value": '{"a":{"b":1}}'}, lambda v: v == {"a.b": 1}),
    ("json.paths", {"value": '{"a":{"b":1}}'}, lambda v: v == ["a.b"]),
    ("json.merge", {"value": '{"a":{"b":1}}', "patch": {"a": {"c": 2}}},
     lambda v: json.loads(v) == {"a": {"b": 1, "c": 2}}),
    ("csv.columns", {"value": "a,b\n1,2"}, lambda v: v == ["a", "b"]),
    ("csv.select", {"value": "a,b\n1,2", "columns": ["b"]}, lambda v: v == "b\n2\n"),
    ("table.unique", {"value": {"columns": ["a"], "rows": [["1"], ["1"], ["2"]]}, "column": "a"},
     lambda v: len(v["rows"]) == 2),
    ("table.limit", {"value": {"columns": ["a"], "rows": [["1"], ["2"]]}, "n": 1},
     lambda v: len(v["rows"]) == 1),
    ("math.percent", {"value": 25, "total": 200}, lambda v: v == 12.5),
    ("math.percentile", {"value": [1, 2, 3, 4], "p": 50}, lambda v: v == 2),
    ("math.gcd", {"value": [12, 18]}, lambda v: v == 6),
    ("math.lcm", {"value": [4, 6]}, lambda v: v == 12),
    ("math.primes", {"limit": 10}, lambda v: v == [2, 3, 5, 7]),
    ("math.base_convert", {"value": "ff", "from_base": 16, "to_base": 10}, lambda v: v == "255"),
    ("date.iso_week", {"value": "2026-01-01"}, lambda v: v["week"] == 1),
    ("date.business_days", {"value": ["2026-01-01", "2026-01-08"]}, lambda v: v == 5),
    ("text.slugify", {"value": "Hello, World!"}, lambda v: v == "hello-world"),
    ("text.rot13", {"value": "uryyb"}, lambda v: v == "hello"),
    ("text.palindrome", {"value": "A man, a plan, a canal: Panama"}, lambda v: v is True),
    ("text.levenshtein", {"value": ["kitten", "sitting"]}, lambda v: v == 3),
    ("email.validate", {"value": "a@example.com"}, lambda v: v["valid"] is True),
    ("ip.validate", {"value": "127.0.0.1"}, lambda v: v["loopback"] is True),
    ("credit_card.luhn", {"value": "4111111111111111"},
     lambda v: v["valid"] is True and v["brand"] == "visa"),
    ("password.entropy", {"value": "abcd"}, lambda v: v["entropy_bits"] == 8),
    ("set.operation", {"a": [1, 2], "b": [2, 3], "op": "union"},
     lambda v: v == ["1", "2", "3"]),
    ("graph.components", {"edges": [["a", "b"], ["c", "d"]]}, lambda v: v == [["a", "b"], ["c", "d"]]),
    ("graph.toposort", {"edges": [["a", "b"], ["b", "c"]]},
     lambda v: v == ["a", "b", "c"]),
    ("xml.to_json", {"value": "<root><a>1</a><b>2</b></root>"},
     lambda v: json.loads(v) == {"root": {"a": "1", "b": "2"}}),
    ("uuid.v5", {"value": "x"}, lambda v: v[14] == "5"),
]


def test_toolbox_registers_every_declared_capability():
    engine = EvolutionEngine(FabricStore(), experts=[])
    names = {cap.name for cap in engine.registry.list_active()}
    assert set(TOOLBOX) <= names
    assert len(engine.registry.list_active()) >= 93
    engine.store.close()


@pytest.mark.parametrize("name,payload,check", CASES)
def test_toolbox_capability_runs_through_the_registry(name, payload, check):
    engine = EvolutionEngine(FabricStore(), experts=[])
    try:
        result = engine.registry.invoke(name, payload)
        assert check(result["value"])
    finally:
        engine.store.close()


def test_toolbox_rejects_bad_input_without_crashing_the_registry():
    engine = EvolutionEngine(FabricStore(), experts=[])
    try:
        with pytest.raises(CapabilityError):
            engine.registry.invoke("hex.decode", {"value": "zz"})
    finally:
        engine.store.close()
