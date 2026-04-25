#!/usr/bin/env bash
# reviewer.sh — review-handler.sh with bounty reporting.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/bounty.sh
source "$SCRIPT_DIR/lib/bounty.sh"

_PR="${ASDLC_PR_NUMBER:-}"
_START=$SECONDS

bounty_report "$(_bounty_payload "reviewer" "working")" || true

_handler="$SCRIPT_DIR/review-handler.sh"
[ -x "$_handler" ] || _handler="${ASDLC_ROOT:?ASDLC_ROOT is required}/scripts/review-handler.sh"

if "$_handler" "$@"; then
    _DUR=$(( SECONDS - _START ))
    bounty_report "$(_bounty_payload "reviewer" "done" "$_DUR" "Review complete")" || true
    if [[ -n "$_PR" ]]; then
        gh pr comment "$_PR" \
            --body "👀 Reviewer: Review complete (${_DUR}s). See inline comments above." \
            2>/dev/null || true
    fi
else
    _rc=$?
    bounty_report "$(_bounty_payload "reviewer" "failed" "$(( SECONDS - _START ))" "Handler failed")" || true
    exit "$_rc"
fi
