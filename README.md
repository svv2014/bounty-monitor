# Bounty Monitor

Generic live dashboard for tracking agent activity, scoring, and AI judge verdicts — works with any pipeline or workflow.

## What it does

- **Live status** — see what any agent or role is doing right now
- **Bounty board** — leaderboard tracking points across all projects and roles
- **Judge verdicts** — post AI-generated or rule-based scores with reasoning
- **Activity feed** — real-time log of all reported events

## Quick start

```bash
pip install fastapi uvicorn
uvicorn server:app --host 127.0.0.1 --port 18792
open http://localhost:18792
```

Report an event from any shell:

```bash
curl -X POST http://localhost:18792/api/report \
  -H 'Content-Type: application/json' \
  -d '{"project":"my-repo","role":"builder","event_type":"working"}'
```

`role` and `event_type` accept **any string** — there is no fixed list.

## Configuration

Copy `bounty-monitor.yaml` and edit as needed:

```yaml
server:
  host: "127.0.0.1"
  port: 18792

scoring:
  roles:           # roles shown on the dashboard status grid
    - builder
    - reviewer
    - tester
```

The config is optional — the server works with zero configuration.

## Stack

- **FastAPI** + **uvicorn** (Python)
- **SQLite** (persistence, zero setup)
- **Vanilla HTML/JS** (dashboard, no build step)

## Architecture

```
Any agent / CI job → POST /api/report → Bounty Monitor → Dashboard
                                              ↑
                              Judge (post-merge) → POST /api/verdict
```

## Clients

| Client | Location | Description |
|--------|----------|-------------|
| Shell | `lib/bounty.sh` | `bounty_report` function — fire-and-forget |
| Python | `lib/client.py` | `BountyClient` class — async or sync |
| GitHub Actions | `.github/actions/bounty-report/` | Reusable composite action |
| curl | `examples/curl/report.sh` | Raw HTTP examples |
| Webhooks | `/api/webhook/github`, `/api/webhook/gitlab` | Receiver skeletons |

## Documentation

- [Integration guide](docs/integration.md) — API reference, client setup, webhooks
- [Scoring](docs/scoring.md) — how points accumulate, customising the scoring table
- [ASDLC integration](docs/asdlc.md) — ASDLC-specific handler scripts and judge

## ASDLC

The ASDLC-specific handler wrappers and judge script live in `examples/asdlc/`. See [docs/asdlc.md](docs/asdlc.md).
