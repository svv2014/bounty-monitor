import json
import os
import tempfile
import pytest

# Use a temp file so all get_db() calls share state
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)

import server
server.DB_PATH = _db_path
server.init_db()

from fastapi.testclient import TestClient
from server import app

client = TestClient(app)


def test_report_accepted():
    resp = client.post("/api/report", json={
        "project": "proj-a",
        "role": "builder",
        "model": "claude-3",
        "event_type": "started",
    })
    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted"}


def test_verdict_accepted():
    resp = client.post("/api/verdict", json={
        "project": "proj-a",
        "role": "builder",
        "model": "claude-3",
        "points": 10,
        "reason": "good work",
    })
    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted"}


def test_board_returns_list():
    server._insert_verdict(server.VerdictPayload(
        project="proj-b", role="reviewer", model="gpt-4", points=5, reason="ok"
    ))
    resp = client.get("/api/board")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    entry = next((r for r in data if r["project"] == "proj-b"), None)
    assert entry is not None
    assert entry["total_points"] == 5


def test_feed_returns_list():
    server._insert_event(server.ReportPayload(
        project="proj-c", role="tester", event_type="finished"
    ))
    resp = client.get("/api/feed")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) <= 50


def test_status_returns_list():
    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_board_cumulative_scores():
    server._insert_verdict(server.VerdictPayload(
        project="proj-d", role="planner", model="claude-3", points=8, reason="first"
    ))
    server._insert_verdict(server.VerdictPayload(
        project="proj-d", role="planner", model="claude-3", points=7, reason="second"
    ))
    resp = client.get("/api/board")
    data = resp.json()
    entry = next(r for r in data if r["project"] == "proj-d" and r["role"] == "planner")
    assert entry["total_points"] == 15
    assert entry["verdict_count"] == 2


# ── Fixture-based tests for dashboard and /api/verdicts ──

@pytest.fixture()
def isolated_client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_load_config", lambda path=None: {})
    monkeypatch.setattr(server, "DB_PATH", str(tmp_path / "test.db"))
    with TestClient(server.app) as c:
        yield c


def test_get_root_returns_dashboard_html(isolated_client):
    response = isolated_client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Bounty Monitor" in response.text


def test_api_verdicts_empty(isolated_client):
    response = isolated_client.get("/api/verdicts")
    assert response.status_code == 200
    assert response.json() == []


def test_api_verdicts_after_post(isolated_client):
    isolated_client.post("/api/verdict", json={
        "project": "test", "role": "builder", "points": 10, "reason": "good work"
    })
    response = isolated_client.get("/api/verdicts")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["role"] == "builder"
    assert data[0]["points"] == 10
    assert data[0]["reason"] == "good work"


# ── issue_history and pipeline_runs tests ──

def test_history_empty(isolated_client):
    response = isolated_client.get("/api/history/proj-x/42")
    assert response.status_code == 200
    assert response.json() == []


def test_history_after_report_with_issue(isolated_client):
    server._insert_event(server.ReportPayload(
        project="proj-h", role="builder", event_type="started",
        issue_number=10, pr_number=5, model="claude-3"
    ))
    response = isolated_client.get("/api/history/proj-h/10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["issue_number"] == 10
    assert data[0]["pr_number"] == 5
    assert data[0]["role"] == "builder"


def test_history_no_entry_without_issue_number(isolated_client):
    server._insert_event(server.ReportPayload(
        project="proj-h2", role="planner", event_type="working"
    ))
    response = isolated_client.get("/api/history/proj-h2/99")
    assert response.status_code == 200
    assert response.json() == []


def test_runs_empty(isolated_client):
    response = isolated_client.get("/api/runs")
    assert response.status_code == 200
    assert response.json() == []


def test_runs_created_after_report(isolated_client):
    server._insert_event(server.ReportPayload(
        project="proj-r", role="builder", event_type="started", issue_number=20
    ))
    response = isolated_client.get("/api/runs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["issue_number"] == 20
    assert data[0]["project"] == "proj-r"


def test_runs_by_project(isolated_client):
    server._insert_event(server.ReportPayload(
        project="proj-p1", role="builder", event_type="done", issue_number=1
    ))
    server._insert_event(server.ReportPayload(
        project="proj-p2", role="builder", event_type="done", issue_number=2
    ))
    response = isolated_client.get("/api/runs/proj-p1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["project"] == "proj-p1"


def test_stats_empty(isolated_client):
    response = isolated_client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_runs" in data
    assert data["total_runs"] == 0


def test_stats_with_runs(isolated_client):
    server._insert_event(server.ReportPayload(
        project="proj-s", role="builder", event_type="done", issue_number=30
    ))
    response = isolated_client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_runs"] >= 1
    assert "avg_duration_seconds" in data
    assert "success_rate" in data
    assert "rework_rate" in data


def test_pipeline_run_not_duplicated(isolated_client):
    server._insert_event(server.ReportPayload(
        project="proj-nd", role="planner", event_type="started", issue_number=50
    ))
    server._insert_event(server.ReportPayload(
        project="proj-nd", role="builder", event_type="done", issue_number=50, pr_number=99
    ))
    response = isolated_client.get("/api/runs/proj-nd")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["pr_number"] == 99


# ── Tests for /api/config/roles ──

def test_config_roles_empty(isolated_client):
    response = isolated_client.get("/api/config/roles")
    assert response.status_code == 200
    data = response.json()
    assert "roles" in data
    assert isinstance(data["roles"], list)


def test_config_roles_from_config(isolated_client, monkeypatch):
    monkeypatch.setitem(server._config, "scoring", {"roles": ["builder", "reviewer", "deployer"]})
    response = isolated_client.get("/api/config/roles")
    assert response.status_code == 200
    assert response.json()["roles"] == ["builder", "reviewer", "deployer"]


# ── Tests for /api/webhook/github ──

def _github_sig(secret: str, body: bytes) -> str:
    import hmac as _hmac, hashlib
    mac = _hmac.new(secret.encode(), body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def test_webhook_github_no_secret(isolated_client):
    payload = json.dumps({"repository": {"full_name": "org/repo"}, "sender": {"login": "user"}})
    response = isolated_client.post(
        "/api/webhook/github",
        content=payload,
        headers={"Content-Type": "application/json", "X-GitHub-Event": "push"},
    )
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}


def test_webhook_github_valid_signature(isolated_client, monkeypatch):
    secret = "test-secret"
    monkeypatch.setenv("BOUNTY_WEBHOOK_SECRET", secret)
    payload = json.dumps({"repository": {"full_name": "org/repo"}, "sender": {"login": "user"}}).encode()
    sig = _github_sig(secret, payload)
    response = isolated_client.post(
        "/api/webhook/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": sig,
        },
    )
    assert response.status_code == 202


def test_webhook_github_invalid_signature(isolated_client, monkeypatch):
    monkeypatch.setenv("BOUNTY_WEBHOOK_SECRET", "real-secret")
    payload = json.dumps({"repository": {"full_name": "org/repo"}}).encode()
    response = isolated_client.post(
        "/api/webhook/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=badhash",
        },
    )
    assert response.status_code == 401


# ── Tests for /api/webhook/gitlab ──

def test_webhook_gitlab_no_secret(isolated_client):
    payload = json.dumps({"project": {"path_with_namespace": "org/repo"}, "user": {"username": "dev"}})
    response = isolated_client.post(
        "/api/webhook/gitlab",
        content=payload,
        headers={"Content-Type": "application/json", "X-Gitlab-Event": "Push Hook"},
    )
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}


def test_webhook_gitlab_valid_token(isolated_client, monkeypatch):
    secret = "gitlab-token"
    monkeypatch.setenv("BOUNTY_WEBHOOK_SECRET", secret)
    payload = json.dumps({"project": {"path_with_namespace": "org/repo"}, "user": {"username": "dev"}}).encode()
    response = isolated_client.post(
        "/api/webhook/gitlab",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Gitlab-Event": "Push Hook",
            "X-Gitlab-Token": secret,
        },
    )
    assert response.status_code == 202


def test_webhook_gitlab_invalid_token(isolated_client, monkeypatch):
    monkeypatch.setenv("BOUNTY_WEBHOOK_SECRET", "real-token")
    payload = json.dumps({}).encode()
    response = isolated_client.post(
        "/api/webhook/gitlab",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Gitlab-Token": "wrong-token",
        },
    )
    assert response.status_code == 401


# ── Test null feed_limit doesn't crash ──

def test_feed_with_null_limit(isolated_client, monkeypatch):
    monkeypatch.setitem(server._config, "retention", {"feed_limit": None})
    response = isolated_client.get("/api/feed")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_verdicts_with_null_limit(isolated_client, monkeypatch):
    monkeypatch.setitem(server._config, "retention", {"verdict_limit": None})
    response = isolated_client.get("/api/verdicts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
