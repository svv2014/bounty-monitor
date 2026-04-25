import sqlite3
import json
import hmac
import hashlib
import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional, Any

from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB_PATH = "bounty.db"
CONFIG_PATH = "bounty-monitor.yaml"

# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _load_config(path: str = CONFIG_PATH) -> dict:
    try:
        import yaml  # type: ignore
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except ImportError:
        return {}


_config: dict = {}


def get_config() -> dict:
    return _config


def get_dashboard_roles() -> list[str]:
    roles = _config.get("scoring", {}).get("roles", [])
    return [r for r in roles if isinstance(r, str)]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            role TEXT NOT NULL,
            model TEXT,
            event_type TEXT NOT NULL,
            payload TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS verdicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            role TEXT NOT NULL,
            model TEXT,
            points INTEGER NOT NULL DEFAULT 0,
            reason TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            role TEXT NOT NULL,
            model TEXT,
            total_points INTEGER NOT NULL DEFAULT 0,
            verdict_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS issue_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            issue_number INTEGER NOT NULL,
            pr_number INTEGER,
            role TEXT NOT NULL,
            event_type TEXT NOT NULL,
            agent TEXT,
            model TEXT,
            duration_seconds INTEGER,
            rework_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            issue_number INTEGER NOT NULL,
            pr_number INTEGER,
            title TEXT,
            outcome TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            total_duration_seconds INTEGER,
            rework_count INTEGER DEFAULT 0,
            total_bounty INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config
    _config = _load_config()
    cfg_server = _config.get("server", {})
    if cfg_server.get("db_path"):
        global DB_PATH
        DB_PATH = cfg_server["db_path"]
    init_db()
    yield


app = FastAPI(title="Bounty Monitor", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ReportPayload(BaseModel):
    project: str
    role: str                       # any string — no hardcoded list
    model: Optional[str] = None
    event_type: str
    payload: Optional[Any] = None
    issue_number: Optional[int] = None
    pr_number: Optional[int] = None
    agent: Optional[str] = None
    duration_seconds: Optional[int] = None
    rework_count: Optional[int] = None


class VerdictPayload(BaseModel):
    project: str
    role: str                       # any string — no hardcoded list
    model: Optional[str] = None
    points: int
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _insert_event(data: ReportPayload):
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO events (project, role, model, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            data.project,
            data.role,
            data.model,
            data.event_type,
            json.dumps(data.payload) if data.payload else None,
            now,
        ),
    )

    if data.issue_number is not None:
        conn.execute(
            """INSERT INTO issue_history
               (project, issue_number, pr_number, role, event_type, agent, model,
                duration_seconds, rework_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.project,
                data.issue_number,
                data.pr_number,
                data.role,
                data.event_type,
                data.agent,
                data.model,
                data.duration_seconds,
                data.rework_count or 0,
                now,
            ),
        )

        existing_run = conn.execute(
            "SELECT id, rework_count FROM pipeline_runs WHERE project=? AND issue_number=?",
            (data.project, data.issue_number),
        ).fetchone()

        if existing_run:
            updates = ["completed_at=?"]
            params: list = [now]
            if data.pr_number is not None:
                updates.append("pr_number=?")
                params.append(data.pr_number)
            if data.rework_count is not None:
                updates.append("rework_count=rework_count+?")
                params.append(data.rework_count)
            params.append(existing_run["id"])
            conn.execute(
                f"UPDATE pipeline_runs SET {', '.join(updates)} WHERE id=?",
                params,
            )
        else:
            conn.execute(
                """INSERT INTO pipeline_runs
                   (project, issue_number, pr_number, started_at, completed_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (data.project, data.issue_number, data.pr_number, now, now, now),
            )

    conn.commit()
    conn.close()


def _insert_verdict(data: VerdictPayload):
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO verdicts (project, role, model, points, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (data.project, data.role, data.model, data.points, data.reason, now),
    )
    existing = conn.execute(
        "SELECT id, total_points, verdict_count FROM scores WHERE project=? AND role=? AND model IS ?",
        (data.project, data.role, data.model),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE scores SET total_points=?, verdict_count=?, updated_at=? WHERE id=?",
            (
                existing["total_points"] + data.points,
                existing["verdict_count"] + 1,
                now,
                existing["id"],
            ),
        )
    else:
        conn.execute(
            "INSERT INTO scores (project, role, model, total_points, verdict_count, updated_at) VALUES (?, ?, ?, ?, 1, ?)",
            (data.project, data.role, data.model, data.points, now),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

@app.post("/api/report", status_code=202)
async def report(data: ReportPayload, background_tasks: BackgroundTasks):
    background_tasks.add_task(_insert_event, data)
    return {"status": "accepted"}


@app.post("/api/verdict", status_code=202)
async def verdict(data: VerdictPayload, background_tasks: BackgroundTasks):
    background_tasks.add_task(_insert_verdict, data)
    return {"status": "accepted"}


@app.get("/api/board")
def board():
    conn = get_db()
    rows = conn.execute(
        "SELECT project, role, model, total_points, verdict_count FROM scores ORDER BY total_points DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/feed")
def feed():
    limit = _config.get("retention", {}).get("feed_limit", 50)
    conn = get_db()
    rows = conn.execute(
        f"SELECT id, project, role, model, event_type, payload, created_at FROM events ORDER BY id DESC LIMIT {int(limit)}"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        entry = dict(r)
        if entry["payload"]:
            entry["payload"] = json.loads(entry["payload"])
        result.append(entry)
    return result


@app.get("/api/status")
def status():
    conn = get_db()
    rows = conn.execute("""
        SELECT e.project, e.role, e.model, e.event_type, e.payload, e.created_at
        FROM events e
        INNER JOIN (
            SELECT project, role, MAX(id) AS max_id FROM events GROUP BY project, role
        ) latest ON e.id = latest.max_id
        ORDER BY e.project, e.role
    """).fetchall()
    conn.close()
    result = []
    for r in rows:
        entry = dict(r)
        if entry["payload"]:
            entry["payload"] = json.loads(entry["payload"])
        result.append(entry)
    return result


@app.get("/api/verdicts")
def get_verdicts():
    limit = _config.get("retention", {}).get("verdict_limit", 50)
    conn = get_db()
    rows = conn.execute(
        f"SELECT id, project, role, model, points, reason, created_at FROM verdicts ORDER BY id DESC LIMIT {int(limit)}"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/history/{project}/{issue}")
def get_history(project: str, issue: int):
    conn = get_db()
    rows = conn.execute(
        """SELECT id, project, issue_number, pr_number, role, event_type, agent, model,
                  duration_seconds, rework_count, created_at
           FROM issue_history
           WHERE project=? AND issue_number=?
           ORDER BY id ASC""",
        (project, issue),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/runs")
def get_runs():
    conn = get_db()
    rows = conn.execute(
        """SELECT id, project, issue_number, pr_number, title, outcome,
                  started_at, completed_at, total_duration_seconds,
                  rework_count, total_bounty, created_at
           FROM pipeline_runs
           ORDER BY id DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/runs/{project}")
def get_runs_by_project(project: str):
    conn = get_db()
    rows = conn.execute(
        """SELECT id, project, issue_number, pr_number, title, outcome,
                  started_at, completed_at, total_duration_seconds,
                  rework_count, total_bounty, created_at
           FROM pipeline_runs
           WHERE project=?
           ORDER BY id DESC""",
        (project,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/stats")
def get_stats():
    conn = get_db()
    row = conn.execute(
        """SELECT
               COUNT(*) AS total_runs,
               AVG(total_duration_seconds) AS avg_duration_seconds,
               ROUND(100.0 * SUM(CASE WHEN outcome = 'clean' THEN 1 ELSE 0 END) / MAX(COUNT(*), 1), 2) AS success_rate,
               ROUND(100.0 * SUM(CASE WHEN rework_count > 0 THEN 1 ELSE 0 END) / MAX(COUNT(*), 1), 2) AS rework_rate
           FROM pipeline_runs"""
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


@app.get("/api/config/roles")
def config_roles():
    return {"roles": get_dashboard_roles()}


# ---------------------------------------------------------------------------
# Webhook skeleton — GitHub / GitLab
# ---------------------------------------------------------------------------

@app.post("/api/webhook/github", status_code=202)
async def webhook_github(request: Request, background_tasks: BackgroundTasks):
    secret = os.environ.get("BOUNTY_WEBHOOK_SECRET", "")
    body = await request.body()

    if secret:
        sig_header = request.headers.get("X-Hub-Signature-256", "")
        mac = hmac.new(secret.encode(), body, hashlib.sha256)
        expected = "sha256=" + mac.hexdigest()
        if not hmac.compare_digest(sig_header, expected):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        event_name = request.headers.get("X-GitHub-Event", "unknown")
        payload = json.loads(body)
        repo = payload.get("repository", {}).get("full_name", "unknown")
        ref = str(payload.get("number") or payload.get("ref", ""))
        sender = payload.get("sender", {}).get("login", "unknown")

        report_data = ReportPayload(
            project=repo,
            role=sender,
            event_type=event_name,
            payload={"ref": ref, "source": "github"},
        )
        background_tasks.add_task(_insert_event, report_data)
    except Exception:
        pass

    return {"status": "accepted"}


@app.post("/api/webhook/gitlab", status_code=202)
async def webhook_gitlab(request: Request, background_tasks: BackgroundTasks):
    secret = os.environ.get("BOUNTY_WEBHOOK_SECRET", "")
    body = await request.body()

    if secret:
        token = request.headers.get("X-Gitlab-Token", "")
        if not hmac.compare_digest(token, secret):
            raise HTTPException(status_code=401, detail="Invalid token")

    try:
        event_name = request.headers.get("X-Gitlab-Event", "unknown")
        payload = json.loads(body)
        project = payload.get("project", {}).get("path_with_namespace", "unknown")
        ref = str(
            payload.get("object_attributes", {}).get("iid")
            or payload.get("ref", "")
        )
        user = payload.get("user", {}).get("username", "unknown")

        report_data = ReportPayload(
            project=project,
            role=user,
            event_type=event_name,
            payload={"ref": ref, "source": "gitlab"},
        )
        background_tasks.add_task(_insert_event, report_data)
    except Exception:
        pass

    return {"status": "accepted"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
