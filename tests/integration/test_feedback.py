import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_feedback_stored_without_github_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    resp = client.post(
        "/api/feedback/",
        json={
            "description": "The pitch view froze after a substitution",
            "context": {"screen": "pitch", "match_id": 3},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "stored"
    assert data["issue_url"] is None

    listed = client.get("/api/feedback/").json()
    assert len(listed) == 1
    assert listed[0]["description"] == "The pitch view froze after a substitution"
    assert listed[0]["context"] == {"screen": "pitch", "match_id": 3}
    assert listed[0]["forwarded"] is False


def test_feedback_forwarded_when_issue_created(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.api.routers import feedback as feedback_module

    monkeypatch.setattr(
        feedback_module,
        "_create_github_issue",
        lambda description, context: "https://github.com/x/y/issues/1",
    )
    resp = client.post("/api/feedback/", json={"description": "Timer does not vibrate"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "reported"
    assert data["issue_url"] == "https://github.com/x/y/issues/1"

    listed = client.get("/api/feedback/").json()
    assert listed[0]["forwarded"] is True
    assert listed[0]["issue_url"] == "https://github.com/x/y/issues/1"


def test_feedback_rejects_empty_description(client: TestClient) -> None:
    assert client.post("/api/feedback/", json={"description": ""}).status_code == 422
