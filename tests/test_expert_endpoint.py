from fastapi.testclient import TestClient

from sovereign.api import create_app


class FakeExpert:
    name = "fake"

    def complete(self, system, user):
        assert "question" in user
        return "external answer"


class BrokenExpert:
    name = "broken"

    def complete(self, system, user):
        raise RuntimeError("down")


def test_expert_ask_returns_text_and_marks_it_unverified(monkeypatch):
    monkeypatch.setattr("sovereign.evolution.default_experts", lambda: [FakeExpert()])
    client = TestClient(create_app())
    response = client.post(
        "/expert/ask",
        json={"question": "question about planning", "system": "be brief"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["expert"] == "fake"
    assert body["answer"] == "external answer"
    assert body["verified"] is False
    assert "unverified" in body["note"]


def test_expert_ask_refuses_when_no_expert_is_configured(monkeypatch):
    monkeypatch.setattr("sovereign.evolution.default_experts", lambda: [])
    client = TestClient(create_app())
    response = client.post("/expert/ask", json={"question": "hello"})
    assert response.status_code == 503


def test_expert_ask_reports_all_failures(monkeypatch):
    monkeypatch.setattr("sovereign.evolution.default_experts", lambda: [BrokenExpert()])
    client = TestClient(create_app())
    response = client.post("/expert/ask", json={"question": "hello"})
    assert response.status_code == 502
    assert response.json()["detail"]["failures"] == ["broken: RuntimeError"]
