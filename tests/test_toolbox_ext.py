import base64
import zlib

import pytest

from sovereign.capabilities import CapabilityError
from sovereign.evolution import EvolutionEngine
from sovereign.store import FabricStore
from sovereign.toolbox_ext import TOOLBOX_EXT


CASES = [
    ("base85.encode", {"value": "hi"}, lambda v: v == base64.b85encode(b"hi").decode()),
    ("base85.decode", {"value": "XlV"}, lambda v: v == "hi"),
    ("zlib.compress", {"value": "hello"}, lambda v: base64.b64decode(v)),
    ("zlib.decompress", {"value": base64.b64encode(zlib.compress(b"hello")).decode()}, lambda v: v == "hello"),
    ("gzip.compress", {"value": "hello"}, lambda v: base64.b64decode(v)[:2] == b"\x1f\x8b"),
    ("gzip.decompress", {"value": "H4sIAAAAAAAAA8tIzcnJBwCGphA2BQAAAA=="}, lambda v: v == "hello"),
    ("stats.correlation", {"x": [1, 2, 3], "y": [2, 4, 6]}, lambda v: v == 1.0),
    ("stats.linear_regression", {"x": [1, 2, 3], "y": [2, 4, 6]},
     lambda v: v["slope"] == 2.0 and v["intercept"] == 0.0 and v["r2"] == 1.0),
    ("stats.zscore", {"value": [1, 2, 3]}, lambda v: v[0] < 0 < v[2]),
    ("stats.bootstrap_ci", {"value": [1, 2, 3], "resamples": 100, "seed": 0},
     lambda v: v["low"] <= v["mean"] <= v["high"]),
    ("stats.moving_average", {"value": [1, 2, 3], "window": 2}, lambda v: v == [1.5, 2.5]),
    ("stats.histogram", {"value": [1, 2, 3, 4], "bins": 2}, lambda v: v["counts"] == [2, 2]),
    ("math.factorial", {"value": 5}, lambda v: v == 120),
    ("math.combinations", {"n": 5, "k": 2}, lambda v: v == 10),
    ("math.fibonacci", {"value": 10}, lambda v: v == 55),
    ("math.is_prime", {"value": 97}, lambda v: v is True),
    ("math.totient", {"value": 9}, lambda v: v == 6),
    ("math.modinv", {"a": 3, "m": 11}, lambda v: v == 4),
    ("date.add_business_days", {"value": "2026-01-01", "days": 1}, lambda v: v == "2026-01-02"),
    ("date.range", {"value": ["2026-01-01", "2026-01-03"]}, lambda v: len(v) == 3),
    ("geo.haversine", {"lat1": 51.5, "lon1": -0.1, "lat2": 48.85, "lon2": 2.35},
     lambda v: 300 < v < 400),
    ("color.hex_to_rgb", {"value": "#ff0000"}, lambda v: v == {"r": 255, "g": 0, "b": 0}),
    ("color.contrast_ratio", {"a": "#000", "b": "#fff"}, lambda v: v == 21.0),
    ("bits.popcount", {"value": 7}, lambda v: v == 3),
    ("bits.xor", {"a": 5, "b": 3}, lambda v: v == 6),
    ("url.validate", {"value": "https://example.com/a"}, lambda v: v["valid"] is True),
    ("domain.validate", {"value": "example.com"}, lambda v: v["valid"] is True),
    ("text.readability", {"value": "This is a simple sentence."},
     lambda v: 0 < v["flesch_reading_ease"] < 100),
    ("text.word_frequency", {"value": "a a b"}, lambda v: v[0] == {"word": "a", "count": 2}),
    ("graph.degree_centrality", {"edges": [["a", "b"], ["a", "c"]]},
     lambda v: v["a"] == 1.0 and v["b"] == 0.5),
    ("graph.clustering_coefficient", {"edges": [["a", "b"], ["b", "c"], ["c", "a"]]},
     lambda v: v["average"] == 1.0),
    ("graph.edge_density", {"edges": [["a", "b"], ["b", "c"], ["c", "a"]]}, lambda v: v == 1.0),
    ("json.pointer", {"value": '{"a":{"b":[10,20]}}', "pointer": "/a/b/1"}, lambda v: v == 20),
    ("json.merge_patch", {"value": '{"a":{"b":1,"c":2}}', "patch": {"a": {"b": None}}},
     lambda v: v == '{"a": {"c": 2}}'),
    ("hash.crc32", {"value": "abc"}, lambda v: v == 891568578),
    ("hash.adler32", {"value": "abc"}, lambda v: v == 38600999),
]


def test_extended_toolbox_registers_every_declared_capability():
    engine = EvolutionEngine(FabricStore(), experts=[])
    try:
        names = {cap.name for cap in engine.registry.list_active()}
        assert set(TOOLBOX_EXT) <= names
        assert len(engine.registry.list_active()) >= 129
    finally:
        engine.store.close()


@pytest.mark.parametrize("name,payload,check", CASES)
def test_extended_capability_runs_through_the_registry(name, payload, check):
    engine = EvolutionEngine(FabricStore(), experts=[])
    try:
        assert check(engine.registry.invoke(name, payload)["value"])
    finally:
        engine.store.close()


def test_extended_toolbox_rejects_bad_compressed_data():
    engine = EvolutionEngine(FabricStore(), experts=[])
    try:
        with pytest.raises(CapabilityError):
            engine.registry.invoke("zlib.decompress", {"value": "not-base64"})
    finally:
        engine.store.close()
