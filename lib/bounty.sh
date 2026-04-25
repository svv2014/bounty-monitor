#!/usr/bin/env bash
# bounty_report — fire-and-forget POST to the bounty monitor; never blocks.
#
# Usage: bounty_report <role> <project> <ref> <event_type> [trigger_judge]
#   role          planner | builder | reviewer | tester | reviser | merger
#   project       project slug ($ASDLC_SLUG)
#   ref           issue or PR number
#   event_type    working | done | failed
#   trigger_judge (optional) true to queue judge verdict on merge

BOUNTY_MONITOR_URL="${BOUNTY_MONITOR_URL:-http://localhost:18792}"

bounty_report() {
    local role="${1:-}" project="${2:-}" ref="${3:-}" event_type="${4:-}" trigger="${5:-false}"
    local issue_number="${6:-}" pr_number="${7:-}"
    local ts
    ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date '+%Y-%m-%dT%H:%M:%SZ')
    local issue_field="" pr_field=""
    if [ -n "$issue_number" ]; then
        issue_field=",\"issue_number\":${issue_number}"
    fi
    if [ -n "$pr_number" ]; then
        pr_field=",\"pr_number\":${pr_number}"
    fi
    local payload
    payload="{\"role\":\"${role}\",\"project\":\"${project}\",\"ref\":\"${ref}\",\"event_type\":\"${event_type}\",\"trigger_judge\":${trigger},\"timestamp\":\"${ts}\"${issue_field}${pr_field}}"
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
