#!/usr/bin/env bash
# tester.sh — qa-handler.sh with bounty reporting.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/bounty.sh
source "$SCRIPT_DIR/lib/bounty.sh"

_PR="${ASDLC_PR_NUMBER:-}"
_START=$SECONDS

bounty_report "$(_bounty_payload "tester" "working")" || true

_handler="$SCRIPT_DIR/qa-handler.sh"
[ -x "$_handler" ] || _handler="${ASDLC_ROOT:?ASDLC_ROOT is required}/scripts/qa-handler.sh"

if "$_handler" "$@"; then
    _DUR=$(( SECONDS - _START ))
    bounty_report "$(_bounty_payload "tester" "done" "$_DUR" "QA passed")" || true
    if [[ -n "$_PR" ]]; then
        gh pr comment "$_PR" \
            --body "🧪 Tester: QA passed (${_DUR}s). No blocking issues found." \
            2>/dev/null || true
    fi
else
    _rc=$?
    bounty_report "$(_bounty_payload "tester" "failed" "$(( SECONDS - _START ))" "QA failed")" || true
    if [[ -n "$_PR" ]]; then
        gh pr comment "$_PR" \
            --body "🧪 Tester: QA failed ($(( SECONDS - _START ))s). See errors above." \
            2>/dev/null || true
    fi
    exit "$_rc"
fi
