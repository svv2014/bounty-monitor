# Bounty Monitor

Local dashboard for the [ASDLC](https://github.com/svv2014/asdlc) pipeline — live agent tracking, bounty scoring, and AI judge verdicts.

## What it does

- **Live status** — see what every pipeline agent (Planner, Builder, Reviewer, Tester) is doing right now
- **Bounty board** — leaderboard tracking agent performance across all projects
- **Judge verdicts** — AI reviews merged work and assigns bounty points with reasoning
- **Activity feed** — real-time log of pipeline events

## Stack

- **FastAPI** + **uvicorn** (Python)
- **SQLite** (persistence)
- **Vanilla HTML/JS** (dashboard — no build step)

## Quick start

```bash
pip install fastapi uvicorn
cd bounty-monitor
uvicorn server:app --host 127.0.0.1 --port 18792
open http://localhost:18792
```

## Architecture

```
ASDLC Handlers → POST /api/report → Bounty Monitor → Dashboard
                                          ↑
                              Judge agent (post-merge) → POST /api/verdict
```

## Status

🚧 Under construction — managed by the ASDLC pipeline itself.
