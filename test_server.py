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
