#!/usr/bin/env bash
# builder.sh — dev-handler.sh with bounty reporting.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/bounty.sh
source "$SCRIPT_DIR/lib/bounty.sh"

_ISSUE="${ASDLC_ISSUE_NUMBER:-}"
_START=$SECONDS

bounty_report "$(_bounty_payload "builder" "working")" || true

_handler="$SCRIPT_DIR/dev-handler.sh"
[ -x "$_handler" ] || _handler="${ASDLC_ROOT:?ASDLC_ROOT is required}/scripts/dev-handler.sh"

if "$_handler" "$@"; then
    _DUR=$(( SECONDS - _START ))
    _PR="${ASDLC_PR_NUMBER:-}"
    bounty_report "$(_bounty_payload "builder" "done" "$_DUR" "Implementation complete")" || true
    if [[ -n "$_ISSUE" ]]; then
        gh issue comment "$_ISSUE" \
            --body "🔨 Builder: Implementation complete (${_DUR}s).${_PR:+ PR #${_PR} opened.}" \
            2>/dev/null || true
    fi
    if [[ -n "$_PR" ]]; then
        gh pr comment "$_PR" \
            --body "🔨 Builder: Implementation complete (${_DUR}s). Opened from issue #${_ISSUE:-?}." \
            2>/dev/null || true
    fi
else
    _rc=$?
    bounty_report "$(_bounty_payload "builder" "failed" "$(( SECONDS - _START ))" "Handler failed")" || true
    exit "$_rc"
fi
