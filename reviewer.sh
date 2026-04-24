#!/usr/bin/env bash
# reviewer.sh — review-handler.sh with bounty reporting.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/bounty.sh
source "$SCRIPT_DIR/lib/bounty.sh"

SLUG="${ASDLC_SLUG:-}"
REF="${ASDLC_PR_NUMBER:-}"

bounty_report "reviewer" "$SLUG" "$REF" "working"

_handler="$SCRIPT_DIR/review-handler.sh"
[ -x "$_handler" ] || _handler="${ASDLC_ROOT:?ASDLC_ROOT is required}/scripts/review-handler.sh"

if "$_handler" "$@"; then
    bounty_report "reviewer" "$SLUG" "$REF" "done"
else
    _rc=$?
    bounty_report "reviewer" "$SLUG" "$REF" "failed"
    exit "$_rc"
fi
