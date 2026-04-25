#!/usr/bin/env bash
# planner.sh — po-handler.sh with bounty reporting.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/bounty.sh
source "$SCRIPT_DIR/lib/bounty.sh"

_ISSUE="${ASDLC_ISSUE_NUMBER:-}"
_START=$SECONDS

bounty_report "$(_bounty_payload "planner" "working")" || true

_handler="$SCRIPT_DIR/po-handler.sh"
[ -x "$_handler" ] || _handler="${ASDLC_ROOT:?ASDLC_ROOT is required}/scripts/po-handler.sh"

if "$_handler" "$@"; then
    _DUR=$(( SECONDS - _START ))
    bounty_report "$(_bounty_payload "planner" "done" "$_DUR" "Spec complete")" || true
    if [[ -n "$_ISSUE" ]]; then
        gh issue comment "$_ISSUE" \
            --body "🎯 Planner: Spec complete (${_DUR}s). Issue #${_ISSUE} ready for implementation." \
            2>/dev/null || true
    fi
else
    _rc=$?
    bounty_report "$(_bounty_payload "planner" "failed" "$(( SECONDS - _START ))" "Handler failed")" || true
    exit "$_rc"
fi
