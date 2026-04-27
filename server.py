import sqlite3
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional, Any

from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB_PATH = "bounty.db"


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
            issue_number INTEGER,
            pr_number INTEGER,
            detail TEXT,
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
    # Migrate existing events table if new columns are missing
    cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    for col, defn in [
        ("issue_number", "INTEGER"),
        ("pr_number", "INTEGER"),
        ("detail", "TEXT"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col} {defn}")

    conn.commit()
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Bounty Monitor", lifespan=lifespan)


class ReportPayload(BaseModel):
    project: str
    role: str
    model: Optional[str] = None
    event_type: str
    payload: Optional[Any] = None
    issue_number: Optional[int] = None
    pr_number: Optional[int] = None
    agent: Optional[str] = None
    detail: Optional[str] = None
    duration_seconds: Optional[int] = None
    rework_count: Optional[int] = None


class VerdictPayload(BaseModel):
    project: str
    role: str
    model: Optional[str] = None
    points: int
    reason: Optional[str] = None


def _insert_event(data: ReportPayload):
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO events
           (project, role, model, event_type, issue_number, pr_number, detail, payload, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.project,
            data.role,
            data.model,
            data.event_type,
            data.issue_number,
            data.pr_number,
            data.detail,
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
    # Upsert into scores
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


@app.get("/api/active")
def active():
    """Currently running workers: latest event per project+role is a *_start within last 4h."""
    conn = get_db()
    rows = conn.execute("""
        SELECT e.project, e.role, e.model, e.event_type, e.issue_number, e.pr_number,
               e.detail, e.created_at
        FROM events e
        INNER JOIN (
            SELECT project, role, MAX(id) AS max_id FROM events GROUP BY project, role
        ) latest ON e.id = latest.max_id
        WHERE e.event_type LIKE '%_start'
          AND e.created_at >= datetime('now', '-4 hours')
        ORDER BY e.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/feed")
def feed():
    conn = get_db()
    rows = conn.execute(
        """SELECT id, project, role, model, event_type, issue_number, pr_number,
                  detail, payload, created_at
           FROM events ORDER BY id DESC LIMIT 50"""
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
        SELECT e.project, e.role, e.model, e.event_type, e.issue_number, e.pr_number,
               e.detail, e.payload, e.created_at
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
    conn = get_db()
    rows = conn.execute(
        "SELECT id, project, role, model, points, reason, created_at FROM verdicts ORDER BY id DESC LIMIT 50"
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


app.mount("/", StaticFiles(directory="static", html=True), name="static")
