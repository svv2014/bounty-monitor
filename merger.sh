#!/usr/bin/env bash
# merger.sh — merge-handler.sh with bounty reporting; triggers judge on merge.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/bounty.sh
source "$SCRIPT_DIR/lib/bounty.sh"

_PR="${ASDLC_PR_NUMBER:-}"
_ISSUE="${ASDLC_ISSUE_NUMBER:-}"
_START=$SECONDS

bounty_report "$(_bounty_payload "merger" "working")" || true

_handler="$SCRIPT_DIR/merge-handler.sh"
[ -x "$_handler" ] || _handler="${ASDLC_ROOT:?ASDLC_ROOT is required}/scripts/merge-handler.sh"

if "$_handler" "$@"; then
    _DUR=$(( SECONDS - _START ))
    bounty_report "$(_bounty_payload "merger" "done" "$_DUR" "Merged" "true")" || true
    if [[ -n "$_PR" ]]; then
        gh pr comment "$_PR" \
            --body "📦 Merger: Merged (${_DUR}s).${_ISSUE:+ Issue #${_ISSUE} closed.}" \
            2>/dev/null || true
    fi
else
    _rc=$?
    bounty_report "$(_bounty_payload "merger" "failed" "$(( SECONDS - _START ))" "Handler failed")" || true
    exit "$_rc"
fi
