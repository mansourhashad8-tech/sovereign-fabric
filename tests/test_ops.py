import pytest
from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.diagnostics import diagnose
from sovereign.evolution import EvolutionEngine
from sovereign.models import Capability, Provenance
from sovereign.store import FabricStore


def test_metrics_and_rate_limit_headers():
    client = TestClient(create_app())
    health = client.get("/health")
    assert health.status_code == 200
    assert health.headers["x-ratelimit-limit"] == "600"
    assert int(health.headers["x-ratelimit-remaining"]) < 600
    text = client.get("/metrics").text
    assert "sovereign_requests_total" in text
    assert 'sovereign_requests_by_status{status="200"}' in text
    assert "sovereign_capabilities 52" in text
    assert "sovereign_knowledge_units" in text


def test_ready_reports_each_dependency():
    client = TestClient(create_app())
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["checks"] == {
        "database": True,
        "capabilities": True,
        "guardians": True,
        "planner": True,
    }


def test_diagnostics_passes_and_detects_a_missing_entry():
    engine = EvolutionEngine(FabricStore())
    clean = diagnose(engine, include_security=False)
    assert clean["ok"] is True
    assert clean["capabilities"] >= 52
    assert clean["issues"] == []

    engine.registry.register(
        Capability(
            name="bad.op",
            description="missing function",
            inputs=("a",),
            outputs=("b",),
            kind="builtin",
            entry="sovereign.extras:missing_function",
            provenance=Provenance(source="builtin", url="", license="internal"),
        )
    )
    broken = diagnose(engine, include_security=False)
    assert broken["ok"] is False
    assert any("capability_entries" in item for item in broken["issues"])


def test_diagnostics_endpoint_is_read_only_and_honest():
    client = TestClient(create_app())
    body = client.get("/diagnostics").json()
    assert body["ok"] is True
    assert body["security"]["findings"]["critical"] == 0
    assert body["security"]["findings"]["high"] == 0
    assert "checks" in body and body["issues"] == []


def test_capability_search_ranks_arithmetic():
    client = TestClient(create_app())
    hits = client.get(
        "/capabilities/search", params={"q": "arithmetic expression", "k": 5}
    ).json()["hits"]
    assert hits
    assert "math.eval" in [hit["name"] for hit in hits[:3]]
    assert hits[0]["score"] > 0


def test_pipeline_composes_capabilities():
    client = TestClient(create_app())
    body = client.post(
        "/pipeline",
        json={
            "steps": [
                {"capability": "text.tokenize", "payload": {"value": "apple banana apple"}},
                {"capability": "tokens.top", "payload": {"limit": 2}},
            ]
        },
    ).json()
    assert body["ok"] is True
    assert body["value"][0] == ["apple", 2]
    assert [step["capability"] for step in body["steps"]] == [
        "text.tokenize",
        "tokens.top",
    ]

    table = client.post(
        "/pipeline",
        json={
            "steps": [
                {"capability": "csv.parse", "payload": {"value": "name,score\nb,2\na,1"}},
                {"capability": "table.aggregate", "payload": {"column": "score", "op": "sum"}},
            ]
        },
    ).json()
    assert table["ok"] is True
    assert table["value"]["result"] == 3.0


def test_pipeline_reports_the_failing_step():
    client = TestClient(create_app())
    body = client.post(
        "/pipeline",
        json={"steps": [{"capability": "math.eval", "payload": {"value": "2+"}}]},
    ).json()
    assert body["ok"] is False
    assert body["failed_at"] == 0
    assert body["error"]
    assert body["steps"] == []


def test_pipeline_is_bounded():
    client = TestClient(create_app())
    steps = [{"capability": "text.clean", "payload": {"value": "x"}}] * 21
    assert client.post("/pipeline", json={"steps": steps}).status_code == 422


def test_rate_limit_denies_and_returns_retry(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_RATE_LIMIT", "1")
    monkeypatch.setenv("SOVEREIGN_RATE_WINDOW", "60")
    client = TestClient(create_app())
    assert client.get("/health").status_code == 200
    denied = client.get("/health")
    assert denied.status_code == 429
    assert denied.headers["x-ratelimit-limit"] == "1"
    assert denied.headers["x-ratelimit-remaining"] == "0"
    assert int(denied.headers["retry-after"]) >= 1


def test_ask_routes_markup_and_config_formats():
    client = TestClient(create_app())

    def ask(request):
        return client.post(
            "/ask", json={"request": request, "sources": ["local"], "budget_s": 1}
        ).json()

    html = ask("html: <h1>Hi</h1><p>There</p>")
    assert html["intent"]["goal_type"] == "text"
    assert html["plan"] == ["html.text"]
    assert html["result"] == "Hi There"

    toml = ask("toml: [a]\nb = 1")
    assert toml["plan"] == ["toml.parse", "json.pretty"]
    assert toml["result"] == '{\n  "a": {\n    "b": 1\n  }\n}'

    headings = ask("عناوين: # A\n## B")
    assert headings["plan"] == ["markdown.headings"]
    assert headings["result"] == [
        {"level": 1, "text": "A"},
        {"level": 2, "text": "B"},
    ]
