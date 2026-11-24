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


def test_graph_endpoint_after_absorb():
    client = _client()
    client.post("/absorb", json={"query": "planning search", "sources": ["local"]})
    graph = client.get("/knowledge/graph", params={"node": "planning"}).json()
    assert "planning" in graph["nodes"]
    assert graph["edges"]


def test_evolve_auto_extend_endpoint():
    client = _client()
    body = client.post(
        "/evolve",
        json={
            "request": "planning text",
            "goal_type": "upper",
            "initial": ["text"],
            "text": "abc",
            "sources": ["local"],
            "auto_extend": True,
            "budget_s": 5.0,
        },
    ).json()
    assert body["plan_solved"] is True
    assert body["plan"][0]["capability"] == "text.upper"
    assert body["execution"]["value"] == "ABC"
    assert body["extensions"]
    assert body["ok"] is False  # local-only: guardianship still fails, honestly


def test_redteam_endpoint_reports_full_coverage():
    body = _client().get("/redteam").json()
    assert body["coverage"] == 1.0
    assert body["evaded"] == []


def test_curriculum_endpoint_local_only_reports_honest_failure():
    body = _client().post(
        "/curriculum", json={"iterations": 2, "sources": ["local"], "budget_s": 5.0}
    ).json()
    assert len(body["results"]) == 2
    assert all(r["ok"] is False for r in body["results"])


def test_experts_endpoint_lists_configuration():
    body = _client().get("/experts").json()
    assert isinstance(body["experts"], list)


def test_execute_batch_endpoint():
    body = _client().post(
        "/execute/batch",
        json={
            "capability": "text.tokenize",
            "payloads": [{"value": "a b"}, {"value": "c"}],
            "mode": "serial",
        },
    ).json()
    assert body["count"] == 2
    assert body["sample"][0] == {"value": ["a", "b"]}


def test_search_cache_and_remote_status():
    client = _client()
    client.post("/absorb", json={"query": "planning", "sources": ["local"]})
    client.get("/knowledge/search", params={"q": "planning", "k": 3})
    client.get("/knowledge/search", params={"q": "planning", "k": 3})
    stats = client.get("/cache/stats").json()
    assert stats["hits"] >= 1
    assert stats["hit_latency_us"] >= 0
    assert client.get("/remote/status").json()["available"] is False


def test_execute_benchmark_endpoint_small():
    body = _client().get(
        "/execute/benchmark", params={"n": 20, "mode": "serial"}
    ).json()
    assert body["count"] == 20
    assert body["duration_s"] > 0


def test_prefetch_makes_a_later_search_a_verified_hit():
    client = _client()
    client.post(
        "/evolve",
        json={
            "request": "markdown report planning",
            "goal_type": "markdown",
            "text": "a b",
            "sources": ["local"],
            "budget_s": 2,
        },
    )
    body = client.get(
        "/knowledge/search", params={"q": "markdown report planning", "k": 2}
    ).json()
    assert body["prefetch_hit"] is True


def test_report_endpoint_is_honest_with_local_only():
    body = _client().get(
        "/report",
        params={
            "query": "planning",
            "sources": "local",
            "budget_s": 3,
            "benchmark_n": 5,
            "benchmark_mode": "serial",
        },
    ).json()
    assert body["ok"] is False
    assert body["guardians"]["ok_sources"] == 1
    assert body["redteam"]["coverage"] == 1.0


def test_report_markdown_endpoint_passes_its_own_audit():
    text = _client().get(
        "/report.md",
        params={
            "query": "planning",
            "sources": "local",
            "budget_s": 3,
            "benchmark_n": 5,
            "benchmark_mode": "serial",
        },
    ).text
    assert text.startswith("# Sovereign system report")
    assert "Verdict" in text


def test_dashboard_serves_a_single_self_contained_page():
    response = _client().get("/dashboard")
    assert response.status_code == 200
    assert "Sovereign" in response.text
    assert "Run full report" in response.text
    assert "https://" not in response.text  # no external assets or CDNs
