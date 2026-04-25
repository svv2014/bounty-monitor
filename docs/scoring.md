# Scoring

Bounty Monitor accumulates points per `(project, role)` pair. Points are added via `POST /api/verdict`. The server does not apply any scoring logic itself — scoring is the responsibility of the caller (judge script, CI job, etc.).

## How scores accumulate

Each verdict call adds `points` to the running `total_points` for that `(project, role, model)` triple. The `verdict_count` increments by 1. Negative points are allowed (penalties).

## Default scoring table (ASDLC example)

The ASDLC judge (`examples/asdlc/judge.sh`) uses the following table:

| Outcome | Planner | Builder | Reviewer | Tester |
|---------|---------|---------|----------|--------|
| `clean` | +3 | +5 | +3 | +2 |
| `rework` | +3 | +2 | +4 | +2 |
| `qa-fail-rework` | +3 | +1 | +1 | +3 |
| `blocked` | -1 | -3 | 0 | 0 |

Bounty bonus: when outcome is `clean` and the linked issue contains `## Bounty: N points`, the bonus is split evenly across all roles.

## Customising scoring

Override the table in `bounty-monitor.yaml`:

```yaml
scoring:
  outcomes:
    clean:
      builder: 10
      reviewer: 5
    rework:
      builder: 3
      reviewer: 6
```

Your judge script reads this config and applies the relevant scores before calling `/api/verdict`.

## Roles

Roles are arbitrary strings. The leaderboard groups by the `role` value you provide. Configure which roles appear on the dashboard status grid under `scoring.roles` in `bounty-monitor.yaml`.

## Leaderboard

`GET /api/board` returns all `(project, role, model, total_points, verdict_count)` rows sorted by `total_points` descending. The dashboard also aggregates across projects per role and per model.
