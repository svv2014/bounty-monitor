#!/usr/bin/env bash
# Curl examples for the Bounty Monitor API.
# Set BOUNTY_MONITOR_URL to point at your server.

BOUNTY_MONITOR_URL="${BOUNTY_MONITOR_URL:-http://localhost:18792}"

# Report that a role has started working
curl -sf -X POST "${BOUNTY_MONITOR_URL}/api/report" \
  -H 'Content-Type: application/json' \
  -d '{"project":"my-project","role":"builder","event_type":"working"}' \
  && echo "reported: working"

# Report completion
curl -sf -X POST "${BOUNTY_MONITOR_URL}/api/report" \
  -H 'Content-Type: application/json' \
  -d '{"project":"my-project","role":"builder","event_type":"done"}' \
  && echo "reported: done"

# Report failure
curl -sf -X POST "${BOUNTY_MONITOR_URL}/api/report" \
  -H 'Content-Type: application/json' \
  -d '{"project":"my-project","role":"builder","event_type":"failed"}' \
  && echo "reported: failed"

# Post a verdict with points and reason
curl -sf -X POST "${BOUNTY_MONITOR_URL}/api/verdict" \
  -H 'Content-Type: application/json' \
  -d '{"project":"my-project","role":"builder","points":5,"reason":"Clean merge, no rework."}' \
  && echo "verdict posted"

# Use any role string you like — the API is not limited to preset values
curl -sf -X POST "${BOUNTY_MONITOR_URL}/api/report" \
  -H 'Content-Type: application/json' \
  -d '{"project":"my-project","role":"deployer","event_type":"working","model":"gpt-4o"}' \
  && echo "reported: deployer working"
