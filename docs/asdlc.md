# ASDLC Integration

Bounty Monitor was originally built for the [ASDLC](https://github.com/svv2014/asdlc) pipeline. The ASDLC-specific handler wrappers live in `examples/asdlc/`.

## Handler scripts

Each script wraps an ASDLC handler with bounty reporting:

| Script | ASDLC handler | Role |
|--------|---------------|------|
| `examples/asdlc/planner.sh` | `po-handler.sh` | planner |
| `examples/asdlc/builder.sh` | `dev-handler.sh` | builder |
| `examples/asdlc/reviewer.sh` | `review-handler.sh` | reviewer |
| `examples/asdlc/tester.sh` | `qa-handler.sh` | tester |
| `examples/asdlc/reviser.sh` | `dev-rework-handler.sh` | reviser |
| `examples/asdlc/merger.sh` | `merge-handler.sh` | merger |

## Setup

1. Copy the handlers you need into your ASDLC project root (or symlink them).
2. Ensure `lib/bounty.sh` is accessible at `../../lib/bounty.sh` relative to the handler, or adjust `BOUNTY_MONITOR_URL` and the source path.
3. Set `BOUNTY_MONITOR_URL` and `ASDLC_SLUG` in your environment.

```bash
export BOUNTY_MONITOR_URL=http://localhost:18792
export ASDLC_SLUG=my-project
export ASDLC_ROOT=/path/to/asdlc
```

## Judge

`examples/asdlc/judge.sh` is the AI judge that runs after a PR is merged:

```bash
scripts/judge.sh <pr_number> [slug]
```

It reads the PR timeline, determines outcome (`clean` / `rework` / `qa-fail-rework` / `blocked`), applies the scoring table, calls the Claude CLI for a verdict summary, and posts per-role verdicts to the monitor.

Trigger it from `examples/asdlc/merger.sh` by passing `trigger_judge=true` to `bounty_report`, or call it directly from a post-merge CI step.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BOUNTY_MONITOR_URL` | `http://localhost:18792` | Monitor server URL |
| `ASDLC_SLUG` | — | Project slug |
| `ASDLC_ISSUE_NUMBER` | — | Current issue number |
| `ASDLC_PR_NUMBER` | — | Current PR number |
| `ASDLC_ROOT` | — | Path to ASDLC scripts directory |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Model for verdict generation |
