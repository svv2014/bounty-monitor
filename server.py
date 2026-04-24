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
    """)
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


@app.get("/api/feed")
def feed():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, project, role, model, event_type, payload, created_at FROM events ORDER BY id DESC LIMIT 50"
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
    # Latest event per project+role
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


app.mount("/", StaticFiles(directory="static", html=True), name="static")
