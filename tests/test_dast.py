"""In-process dynamic checks: malformed input, injection-shaped input, routing."""

from fastapi.testclient import TestClient

from sovereign.api import create_app


def _client():
    return TestClient(create_app())


def test_sql_injection_shaped_query_is_not_executed():
    response = _client().get(
        "/knowledge/search", params={"q": "' OR 1=1 --", "k": 10}
    )
    assert response.status_code == 200
    assert "hits" in response.json()


def test_invalid_json_returns_422_not_500():
    response = _client().post(
        "/verify_claim", content=b"{", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422


def test_xss_payload_is_json_not_html():
    response = _client().post(
        "/verify_claim", json={"claim": "<script>alert(1)</script>"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


def test_unknown_route_is_404():
    assert _client().get("/not-a-route").status_code == 404


def test_wrong_method_is_405():
    assert _client().get("/verify_claim").status_code == 405


def test_oversized_query_is_422():
    response = _client().post("/brief", json={"query": "x" * 501})
    assert response.status_code == 422


def test_security_headers_on_dashboard():
    response = _client().get("/dashboard")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
