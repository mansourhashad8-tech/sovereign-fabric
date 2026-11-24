from fastapi.testclient import TestClient

from sovereign.api import create_app
from sovereign.guard import ApiKey, RateLimiter, security_headers


def test_api_key_is_opt_in_and_constant_time_checked():
    assert ApiKey("").enabled is False
    assert ApiKey("").allows(None) is True
    guard = ApiKey("secret")
    assert guard.enabled is True
    assert guard.allows("secret") is True
    assert guard.allows("wrong") is False
    assert guard.allows(None) is False


def test_rate_limiter_slides_and_reports_retry():
    limiter = RateLimiter(limit=2, window_s=10)
    assert limiter.check("a", now=0).allowed is True
    assert limiter.check("a", now=1).allowed is True
    denied = limiter.check("a", now=2)
    assert denied.allowed is False
    assert denied.retry_after > 0
    assert limiter.check("a", now=11).allowed is True
    assert limiter.check("b", now=11).allowed is True


def test_security_headers_are_restrictive():
    headers = security_headers()
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


def test_health_carries_security_headers():
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "X-RateLimit-Remaining" in response.headers


def test_mutating_endpoint_requires_key_when_configured(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_API_KEY", "secret")
    client = TestClient(create_app())
    assert client.post("/verify_claim", json={"claim": "x"}).status_code == 401
    assert (
        client.post(
            "/verify_claim", json={"claim": "x"}, headers={"X-API-Key": "wrong"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/verify_claim", json={"claim": "x"}, headers={"X-API-Key": "secret"}
        ).status_code
        == 200
    )


def test_oversized_body_is_rejected(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_MAX_BODY", "10")
    client = TestClient(create_app())
    response = client.post(
        "/verify_claim",
        content=b"{}" * 100,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_RATE_LIMIT", "2")
    monkeypatch.setenv("SOVEREIGN_RATE_WINDOW", "60")
    client = TestClient(create_app())
    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 200
    response = client.get("/health")
    assert response.status_code == 429
    assert response.headers.get("Retry-After")
