import base64
import io
import wave

import pytest

from sovereign.capabilities import CapabilityRegistry
from sovereign.extras import bootstrap_extras
from sovereign.graphalg import pagerank, shortest_path
from sovereign.media import image_info, wav_info
from sovereign.store import FabricStore

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nXQAAAAASUVORK5CYII="


def _wav_base64() -> str:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 800)
    return base64.b64encode(buffer.getvalue()).decode()


def test_png_and_wav_headers_are_read_without_decoding_content():
    assert image_info({"value": PNG}) == {
        "format": "png",
        "width": 1,
        "height": 1,
        "bytes": 68,
        "bit_depth": 8,
        "color_type": 4,
    }
    wav = wav_info({"value": _wav_base64()})
    assert wav["channels"] == 1
    assert wav["sample_rate"] == 8000
    assert wav["duration_s"] == 0.1


def test_media_rejects_bad_or_oversized_input():
    with pytest.raises(ValueError):
        image_info({"value": "not base64"})
    with pytest.raises(ValueError):
        image_info({"value": base64.b64encode(b"not an image").decode()})
    with pytest.raises(ValueError):
        wav_info({"value": base64.b64encode(b"not a wav").decode()})


def test_dijkstra_and_pagerank_are_deterministic():
    path = shortest_path(
        {"edges": [["a", "b", 1], ["b", "c", 2], ["a", "c", 5]], "start": "a", "end": "c"}
    )["value"]
    assert path["path"] == ["a", "b", "c"]
    assert path["distance"] == 3.0
    ranked = pagerank({"edges": [["a", "c", 1], ["b", "c", 1], ["c", "a", 1]]})["value"]
    assert abs(sum(ranked["scores"].values()) - 1.0) < 1e-9
    assert ranked["scores"]["c"] > ranked["scores"]["a"] > 0
    with pytest.raises(ValueError):
        shortest_path({"edges": [["a", "b", 1]], "start": "a", "end": "z"})


def test_media_and_graph_capabilities_are_registered():
    registry = CapabilityRegistry(FabricStore())
    bootstrap_extras(registry)
    for name in ("image.info", "audio.wav_info", "graph.shortest_path", "graph.pagerank"):
        assert registry.active(name) is not None
