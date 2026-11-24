import pytest
from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.capabilities import CapabilityError
from sovereign.evolution import EvolutionEngine
from sovereign.store import FabricStore


def _engine():
    return EvolutionEngine(FabricStore())


def test_extras_are_registered_and_idempotent():
    engine = _engine()
    names = {cap.name for cap in engine.registry.list_active()}
    assert len(names) >= 30
    assert {
        "json.validate",
        "csv.parse",
        "math.eval",
        "date.diff",
        "url.parse",
        "text.keywords",
        "text.redact",
        "table.sort",
        "markdown.table",
    } <= names
    before = len(names)
    from sovereign.extras import bootstrap_extras

    bootstrap_extras(engine.registry)
    assert len(engine.registry.list_active()) == before


def test_keywords_and_stats():
    engine = _engine()
    keywords = engine.registry.invoke(
        "text.keywords", {"value": "search search plan plan the", "limit": 2}
    )
    assert keywords["value"] == [
        {"term": "plan", "count": 2},
        {"term": "search", "count": 2},
    ]
    stats = engine.registry.invoke("text.stats", {"value": "a b a. c"})
    assert stats["value"]["words"] == 4
    assert stats["value"]["unique_words"] == 3


def test_redaction_hides_email_ip_and_phone():
    engine = _engine()
    result = engine.registry.invoke(
        "text.redact", {"value": "a@b.com 192.168.1.1 1234567890"}
    )
    assert result["value"] == "[EMAIL] [IP] [PHONE]"
    assert result["replacements"] == 3


def test_json_validation_is_total():
    engine = _engine()
    assert engine.registry.invoke("json.validate", {"value": "{"})["value"]["valid"] is False
    assert engine.registry.invoke("json.validate", {"value": "[1,2]"})["value"] == {
        "valid": True,
        "type": "list",
    }


def test_csv_table_sort_filter_and_markdown():
    engine = _engine()
    table = engine.registry.invoke(
        "csv.parse", {"value": "name,score\nb,2\na,1"}
    )["value"]
    assert table["columns"] == ["name", "score"]
    sorted_table = engine.registry.invoke(
        "table.sort", {"value": table, "column": "score"}
    )["value"]
    assert [row[0] for row in sorted_table["rows"]] == ["a", "b"]
    filtered = engine.registry.invoke(
        "table.filter", {"value": table, "column": "name", "equals": "a"}
    )["value"]
    assert filtered["matched"] == 1
    rendered = engine.registry.invoke("markdown.table", {"value": table})["value"]
    assert rendered.startswith("| name | score |")


def test_math_accepts_arithmetic_and_rejects_names():
    engine = _engine()
    assert engine.registry.invoke("math.eval", {"value": "2*(3+4)"})["value"] == 14
    with pytest.raises(CapabilityError):
        engine.registry.invoke("math.eval", {"value": "__import__('os')"})
    with pytest.raises(CapabilityError):
        engine.registry.invoke("math.eval", {"value": "2**100000"})


def test_dates_urls_base64_and_hash():
    engine = _engine()
    assert engine.registry.invoke(
        "date.diff", {"value": "2026-01-01 2026-01-11"}
    )["value"]["days"] == 10
    assert engine.registry.invoke(
        "url.parse", {"value": "https://example.com/a?b=1#c"}
    )["value"]["netloc"] == "example.com"
    encoded = engine.registry.invoke("base64.encode", {"value": "hello"})["value"]
    assert encoded == "aGVsbG8="
    assert engine.registry.invoke("base64.decode", {"value": encoded})["value"] == "hello"
    assert len(engine.registry.invoke("hash.sha256", {"value": "hello"})["value"]) == 64


def test_api_invoke_runs_any_active_capability():
    client = TestClient(create_app())
    response = client.post(
        "/invoke", json={"capability": "math.eval", "payload": {"value": "2+2"}}
    )
    assert response.status_code == 200
    assert response.json()["result"]["value"] == 4
    missing = client.post("/invoke", json={"capability": "no.such", "payload": {}})
    assert missing.status_code == 400


def test_ask_routes_keywords_and_json_to_new_goals():
    client = TestClient(create_app())
    keywords = client.post(
        "/ask",
        json={
            "request": "كلمات مفتاحية: الذكاء الاصطناعي الاصطناعي",
            "sources": ["local"],
            "budget_s": 1,
        },
    ).json()
    assert keywords["intent"]["goal_type"] == "keywords"
    assert keywords["plan"] == ["text.keywords"]
    assert keywords["result"][0]["term"] == "الاصطناعي"

    pretty = client.post(
        "/ask",
        json={"request": 'json: {"a":1}', "sources": ["local"], "budget_s": 1},
    ).json()
    assert pretty["intent"]["goal_type"] == "json_pretty"
    assert pretty["plan"] == ["json.pretty"]
    assert '"a": 1' in pretty["result"]
