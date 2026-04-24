#!/usr/bin/env bash
# bounty_report — fire-and-forget POST to the bounty monitor; never blocks.
#
# Usage: bounty_report <handler> <slug> <ref> <status> [trigger_judge]
#   handler       planner | builder | reviewer | tester | reviser | merger
#   slug          project slug ($ASDLC_SLUG)
#   ref           issue or PR number
#   status        working | done | failed
#   trigger_judge (optional) true to queue judge verdict on merge

BOUNTY_MONITOR_URL="${BOUNTY_MONITOR_URL:-http://localhost:18792}"

bounty_report() {
    local handler="${1:-}" slug="${2:-}" ref="${3:-}" status="${4:-}" trigger="${5:-false}"
    local ts
    ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date '+%Y-%m-%dT%H:%M:%SZ')
    local payload
    payload="{\"handler\":\"${handler}\",\"slug\":\"${slug}\",\"ref\":\"${ref}\",\"status\":\"${status}\",\"trigger_judge\":${trigger},\"timestamp\":\"${ts}\"}"
    curl -sf \
        --max-time 3 \
        --connect-timeout 2 \
        -X POST \
        -H 'Content-Type: application/json' \
        -d "${payload}" \
        "${BOUNTY_MONITOR_URL}/api/report" \
        >/dev/null 2>&1 &
    disown "$!" 2>/dev/null || true
}
