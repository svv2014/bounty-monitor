# Integration Guide

Bounty Monitor exposes a simple HTTP API. Any agent, CI job, or script can report events and receive verdicts — no special framework required.

## Quick integration

### 1. Start the server

```bash
pip install fastapi uvicorn
uvicorn server:app --host 127.0.0.1 --port 18792
```

### 2. Report events

```bash
curl -X POST http://localhost:18792/api/report \
  -H 'Content-Type: application/json' \
  -d '{"project":"my-repo","role":"builder","event_type":"working"}'
```

`role` and `event_type` accept any string — there is no fixed list.

### 3. Post verdicts

```bash
curl -X POST http://localhost:18792/api/verdict \
  -H 'Content-Type: application/json' \
  -d '{"project":"my-repo","role":"builder","points":5,"reason":"Clean merge."}'
```

---

## Clients

### Shell (lib/bounty.sh)

Source the library and call `bounty_report`:

```bash
source lib/bounty.sh
bounty_report "builder" "my-project" "42" "working"
# ... do work ...
bounty_report "builder" "my-project" "42" "done"
```

`BOUNTY_MONITOR_URL` controls the target (default: `http://localhost:18792`).

### Python (lib/client.py)

```python
from lib.client import BountyClient

c = BountyClient("http://localhost:18792")
c.report(project="my-project", role="builder", event_type="working")
# ... do work ...
c.report(project="my-project", role="builder", event_type="done")
c.verdict(project="my-project", role="builder", points=5, reason="Good.")
```

Calls are fire-and-forget (async background thread) by default. Pass `async_fire=False` for synchronous use.

### GitHub Actions

```yaml
- uses: ./github/actions/bounty-report
  with:
    project: ${{ github.repository }}
    role: builder
    event_type: done
    bounty_monitor_url: ${{ secrets.BOUNTY_MONITOR_URL }}
```

See `.github/actions/bounty-report/action.yml` for the full action definition.

---

## Webhooks

Bounty Monitor includes receiver skeletons for GitHub and GitLab webhooks.

### GitHub

Point a GitHub webhook at `POST /api/webhook/github` (any event type).

Set `BOUNTY_WEBHOOK_SECRET` env var to your webhook secret for signature verification. The receiver maps `sender.login` → `role` and the event name → `event_type`.

### GitLab

Point a GitLab webhook at `POST /api/webhook/gitlab`.

Set `BOUNTY_WEBHOOK_SECRET` to your GitLab webhook token. The receiver maps `user.username` → `role` and the GitLab event header → `event_type`.

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/report` | Log an agent event |
| POST | `/api/verdict` | Record a scoring verdict |
| GET | `/api/board` | Leaderboard (scores by project/role) |
| GET | `/api/feed` | Last N events |
| GET | `/api/status` | Latest event per project+role |
| GET | `/api/verdicts` | Last N verdicts |
| GET | `/api/config/roles` | Dashboard role list from config |
| POST | `/api/webhook/github` | GitHub webhook receiver |
| POST | `/api/webhook/gitlab` | GitLab webhook receiver |

### ReportPayload

```json
{
  "project": "string (required)",
  "role":    "string (required) — any value",
  "event_type": "string (required) — any value",
  "model":   "string (optional)",
  "payload": "any (optional)"
}
```

### VerdictPayload

```json
{
  "project": "string (required)",
  "role":    "string (required)",
  "points":  "integer (required)",
  "model":   "string (optional)",
  "reason":  "string (optional)"
}
```
