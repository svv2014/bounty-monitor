#!/usr/bin/env bash
# scanner.sh — scan a GitHub project for open issues/PRs and post a queue snapshot.
#
# Usage: scanner.sh [slug]
#   slug   project slug (falls back to $ASDLC_SLUG)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/bounty.sh
source "$SCRIPT_DIR/lib/bounty.sh"

SLUG="${1:-${ASDLC_SLUG:-}}"

# Map GitHub labels to queue statuses
_label_to_status() {
    local labels="$1"
    if echo "$labels" | grep -qiE 'blocked|on-hold'; then
        echo "blocked"
    elif echo "$labels" | grep -qiE 'in-progress|in-flight|wip'; then
        echo "in-flight"
    else
        echo "queued"
    fi
}

# Map priority labels to integers (higher = more urgent)
_label_to_priority() {
    local labels="$1"
    if echo "$labels" | grep -qi 'priority:high\|p0\|critical'; then
        echo "3"
    elif echo "$labels" | grep -qi 'priority:medium\|p1'; then
        echo "2"
    elif echo "$labels" | grep -qi 'priority:low\|p2'; then
        echo "1"
    else
        echo "0"
    fi
}

scan_project() {
    local project="${1:-$SLUG}"
    [ -n "$project" ] || { echo "scan_project: project slug required" >&2; return 1; }

    # Fetch open issues (exclude PRs) as JSON
    local issues_json
    issues_json=$(gh issue list \
        --state open \
        --json number,title,url,labels \
        --limit 100 \
        2>/dev/null || echo "[]")

    # Build items JSON array via python3
    # Write the script to a temp file so stdin is free for issues_json piped in.
    local _py_tmp
    _py_tmp=$(mktemp /tmp/scanner_XXXXXX.py)
    cat > "$_py_tmp" <<'PYEOF'
import sys, json

project = sys.argv[1]
raw = sys.stdin.read().strip()
issues = json.loads(raw) if raw else []

items = []
for issue in issues:
    number = str(issue.get("number", ""))
    title  = issue.get("title", "")
    url    = issue.get("url", "")
    labels = " ".join(l.get("name", "") for l in issue.get("labels", []))

    # status
    if any(kw in labels.lower() for kw in ("blocked", "on-hold")):
        status = "blocked"
    elif any(kw in labels.lower() for kw in ("in-progress", "in-flight", "wip")):
        status = "in-flight"
    else:
        status = "queued"

    # priority
    if any(kw in labels.lower() for kw in ("priority:high", "p0", "critical")):
        priority = 3
    elif any(kw in labels.lower() for kw in ("priority:medium", "p1")):
        priority = 2
    elif any(kw in labels.lower() for kw in ("priority:low", "p2")):
        priority = 1
    else:
        priority = 0

    items.append({
        "ref":      number,
        "status":   status,
        "priority": priority,
        "title":    title,
        "url":      url,
    })

print(json.dumps(items))
PYEOF
    local items_json
    items_json=$(echo "$issues_json" | python3 "$_py_tmp" "$project")
    rm -f "$_py_tmp"

    # Post snapshot to bounty monitor (fire-and-forget)
    bounty_report_queue "$project" "$items_json"
}

# Run if invoked directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    scan_project "$SLUG"
fi
