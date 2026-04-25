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


# ── Retention / cleanup tests ─────────────────────────────────────────────────

def test_admin_cleanup_deletes_old_events(isolated_client):
    # Insert an event with a very old timestamp directly
    import sqlite3
    db_path = server.DB_PATH
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO events (project, role, model, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("old-proj", "builder", None, "started", None, "2000-01-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    resp = isolated_client.post("/api/admin/cleanup?retention_days=90")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted_events"] >= 1
    assert data["retention_days"] == 90


def test_admin_cleanup_keeps_scores(isolated_client):
    server._insert_verdict(server.VerdictPayload(
        project="keep-proj", role="tester", model=None, points=3, reason="test"
    ))
    isolated_client.post("/api/admin/cleanup?retention_days=0")
    resp = isolated_client.get("/api/board")
    data = resp.json()
    entry = next((r for r in data if r["project"] == "keep-proj"), None)
    assert entry is not None, "scores must survive cleanup"


def test_prune_old_events_removes_stale():
    old_cutoff = server.BOUNTY_RETENTION_DAYS
    conn = server.get_db()
    conn.execute(
        "INSERT INTO events (project, role, model, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("stale", "planner", None, "done", None, "1999-06-15T12:00:00+00:00"),
    )
    conn.commit()
    conn.close()
    deleted = server._prune_old_events(retention_days=1)
    assert deleted >= 1


# ── Export tests ───────────────────────────────────────────────────────────────

def test_export_events_csv(isolated_client):
    server._insert_event(server.ReportPayload(project="exp-p", role="builder", event_type="start"))
    resp = isolated_client.get("/api/export/events?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    lines = resp.text.strip().splitlines()
    assert lines[0] == "id,project,role,model,event_type,payload,created_at"
    assert len(lines) >= 2


def test_export_events_csv_date_filter(isolated_client):
    server._insert_event(server.ReportPayload(project="filter-p", role="builder", event_type="done"))
    resp = isolated_client.get("/api/export/events?format=csv&from=2000-01-01&to=2099-12-31")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


def test_export_runs_csv(isolated_client):
    resp = isolated_client.get("/api/export/runs?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    lines = resp.text.strip().splitlines()
    assert lines[0] == "id,project,role,model,status,started_at,finished_at"


def test_export_board_json(isolated_client):
    server._insert_verdict(server.VerdictPayload(
        project="board-exp", role="reviewer", model=None, points=7, reason="nice"
    ))
    resp = isolated_client.get("/api/export/board?format=json")
    assert resp.status_code == 200
    data = resp.json()
    assert "exported_at" in data
    assert "board" in data
    assert isinstance(data["board"], list)
    entry = next((r for r in data["board"] if r["project"] == "board-exp"), None)
    assert entry is not None
    assert entry["total_points"] == 7
