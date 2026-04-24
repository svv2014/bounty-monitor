#!/usr/bin/env bash
# planner.sh — po-handler.sh with bounty reporting.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/bounty.sh
source "$SCRIPT_DIR/lib/bounty.sh"

SLUG="${ASDLC_SLUG:-}"
REF="${ASDLC_ISSUE_NUMBER:-}"

bounty_report "planner" "$SLUG" "$REF" "working"

_handler="$SCRIPT_DIR/po-handler.sh"
[ -x "$_handler" ] || _handler="${ASDLC_ROOT:?ASDLC_ROOT is required}/scripts/po-handler.sh"

if "$_handler" "$@"; then
    bounty_report "planner" "$SLUG" "$REF" "done"
else
    _rc=$?
    bounty_report "planner" "$SLUG" "$REF" "failed"
    exit "$_rc"
fi
