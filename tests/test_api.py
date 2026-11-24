from fastapi.testclient import TestClient

from sovereign.api import create_app


def _client() -> TestClient:
    return TestClient(create_app(":memory:"))


def test_root_and_health():
    client = _client()
    root = client.get("/")
    assert root.status_code == 200
    assert "endpoints" in root.json()

    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert "text.tokenize" in {
        c["name"] for c in client.get("/capabilities").json()["capabilities"]
    }


def test_consult_with_local_source():
    client = _client()
    response = client.post(
        "/consult", json={"query": "priority queue search", "sources": ["local"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sources"]["local"] == "ok"
    assert isinstance(body["units"], list)


def test_absorb_then_search():
    client = _client()
    client.post("/absorb", json={"query": "planning search", "sources": ["local"]})
    hits = client.get("/knowledge/search", params={"q": "planning", "k": 3}).json()["hits"]
    assert hits


def test_synthesize_endpoint_admits():
    client = _client()
    response = client.post(
        "/synthesize",
        json={
            "name": "text.upper",
            "description": "uppercase",
            "inputs": ["text"],
            "outputs": ["upper"],
            "spec": {"op": "upper"},
            "examples": [({"value": "abc"}, {"value": "ABC"})],
        },
    )
    body = response.json()
    assert body["admitted"] is True
    assert body["version"] == 1


def test_validate_endpoint():
    client = _client()
    good = client.post(
        "/validate",
        json={
            "subject": "subject",
            "claims": ["did work"],
            "evidence": [{"kind": "consultation", "detail": "2 units", "ref": "a,b"}],
            "context": {
                "sources_ok": 2,
                "external_sources_ok": 2,
                "units_total": 2,
                "fresh_units": 2,
                "deterministic": True,
                "duration_s": 0.1,
                "budget_s": 5.0,
                "constraints_declared": 1,
                "constraints_addressed": 1,
            },
        },
    ).json()
    assert good["passed"] is True

    bad = client.post(
        "/validate",
        json={"subject": "a million times faster", "claims": [], "evidence": []},
    ).json()
    assert bad["passed"] is False
    assert bad["overclaims"]


def test_evolve_endpoint_local_only_is_honest():
    client = _client()
    body = client.post(
        "/evolve",
        json={
            "request": "planning search text",
            "sources": ["local"],
            "text": "a b a",
            "budget_s": 5.0,
        },
    ).json()
    assert body["plan_solved"] is True
    assert body["execution"]["ok"] is True
    assert body["validation"]["passed"] is False
    assert body["ok"] is False


def test_cycles_endpoint_records_run():
    client = _client()
    client.post(
        "/evolve",
        json={"request": "planning search text", "sources": ["local"], "text": "x"},
    )
    cycles = client.get("/cycles").json()["cycles"]
    assert cycles
    assert cycles[0]["kind"] == "cycle"
