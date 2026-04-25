#!/usr/bin/env bash
# reviser.sh — dev-rework-handler.sh with bounty reporting.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/bounty.sh
source "$SCRIPT_DIR/lib/bounty.sh"

_PR="${ASDLC_PR_NUMBER:-}"
_START=$SECONDS

bounty_report "$(_bounty_payload "reviser" "working")" || true

_handler="$SCRIPT_DIR/dev-rework-handler.sh"
[ -x "$_handler" ] || _handler="${ASDLC_ROOT:?ASDLC_ROOT is required}/scripts/dev-rework-handler.sh"

if "$_handler" "$@"; then
    _DUR=$(( SECONDS - _START ))
    _RC="${ASDLC_REWORK_COUNT:-}"
    bounty_report "$(_bounty_payload "reviser" "done" "$_DUR" "Rework complete")" || true
    if [[ -n "$_PR" ]]; then
        gh pr comment "$_PR" \
            --body "🔧 Reviser: Rework complete (${_DUR}s).${_RC:+ Cycle #${_RC}.} PR #${_PR} updated." \
            2>/dev/null || true
    fi
else
    _rc=$?
    bounty_report "$(_bounty_payload "reviser" "failed" "$(( SECONDS - _START ))" "Handler failed")" || true
    exit "$_rc"
fi
