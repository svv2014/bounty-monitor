#!/usr/bin/env bash
# bounty_report — fire-and-forget POST to the bounty monitor; never blocks.
#
# New API:    bounty_report <json_payload>
# Legacy API: bounty_report <role> <project> <ref> <event_type> [trigger_judge]
#
# Helper: _bounty_payload <role> <event_type> [duration_seconds] [detail] [trigger_judge]
#   Builds full JSON from env vars (ASDLC_SLUG, ASDLC_REPO, ASDLC_ISSUE_NUMBER,
#   ASDLC_ISSUE_TITLE, ASDLC_ISSUE_URL, ASDLC_PR_NUMBER, ASDLC_PR_URL,
#   ASDLC_AGENT, ASDLC_AGENT_MODEL, ASDLC_REWORK_COUNT) + explicit args.

BOUNTY_MONITOR_URL="${BOUNTY_MONITOR_URL:-http://localhost:18792}"

_bounty_payload() {
    local role="$1" event_type="$2" duration="${3:-}" detail="${4:-}" trigger="${5:-false}"
    local ts
    ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date '+%Y-%m-%dT%H:%M:%SZ')
    _BP_ROLE="$role" _BP_EVENT="$event_type" _BP_DURATION="$duration" \
    _BP_DETAIL="$detail" _BP_TRIGGER="$trigger" _BP_TS="$ts" \
    python3 -c "
import json, os
def _int(v): return int(v) if v and str(v).strip().isdigit() else None
def _bool(v): return str(v).lower() == 'true'
print(json.dumps({
    'role':             os.environ['_BP_ROLE'],
    'project':          os.environ.get('ASDLC_SLUG') or None,
    'slug':             os.environ.get('ASDLC_SLUG') or None,
    'repo':             os.environ.get('ASDLC_REPO') or None,
    'issue_number':     _int(os.environ.get('ASDLC_ISSUE_NUMBER', '')),
    'issue_title':      os.environ.get('ASDLC_ISSUE_TITLE') or None,
    'issue_url':        os.environ.get('ASDLC_ISSUE_URL') or None,
    'pr_number':        _int(os.environ.get('ASDLC_PR_NUMBER', '')),
    'pr_url':           os.environ.get('ASDLC_PR_URL') or None,
    'agent':            os.environ.get('ASDLC_AGENT') or None,
    'model':            os.environ.get('ASDLC_AGENT_MODEL') or os.environ.get('CLAUDE_MODEL') or None,
    'event_type':       os.environ['_BP_EVENT'],
    'duration_seconds': _int(os.environ.get('_BP_DURATION', '')),
    'detail':           os.environ.get('_BP_DETAIL') or None,
    'rework_count':     _int(os.environ.get('ASDLC_REWORK_COUNT', '')) or 0,
    'trigger_judge':    _bool(os.environ['_BP_TRIGGER']),
    'timestamp':        os.environ['_BP_TS'],
}))
" 2>/dev/null || printf '{"role":"%s","event_type":"%s","timestamp":"%s"}' "$role" "$event_type" "$ts"
}

bounty_report() {
    local payload
    if [[ "${1:-}" == "{"* ]]; then
        payload="$1"
    else
        # Legacy positional: bounty_report <role> <project> <ref> <event_type> [trigger_judge]
        local role="${1:-}" project="${2:-}" ref="${3:-}" event_type="${4:-}" trigger="${5:-false}"
        local ts
        ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date '+%Y-%m-%dT%H:%M:%SZ')
        payload="{\"role\":\"${role}\",\"project\":\"${project}\",\"ref\":\"${ref}\",\"event_type\":\"${event_type}\",\"trigger_judge\":${trigger},\"timestamp\":\"${ts}\"}"
    fi
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
