#!/usr/bin/env bash
# tester.sh — qa-handler.sh with bounty reporting.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../../lib/bounty.sh
source "$SCRIPT_DIR/../../lib/bounty.sh"

SLUG="${ASDLC_SLUG:-}"
REF="${ASDLC_PR_NUMBER:-}"

bounty_report "tester" "$SLUG" "$REF" "working"

_handler="$SCRIPT_DIR/qa-handler.sh"
[ -x "$_handler" ] || _handler="${ASDLC_ROOT:?ASDLC_ROOT is required}/scripts/qa-handler.sh"

if "$_handler" "$@"; then
    bounty_report "tester" "$SLUG" "$REF" "done"
else
    _rc=$?
    bounty_report "tester" "$SLUG" "$REF" "failed"
    exit "$_rc"
fi
