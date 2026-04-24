#!/usr/bin/env bash
# reviser.sh — dev-rework-handler.sh with bounty reporting.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/bounty.sh
source "$SCRIPT_DIR/lib/bounty.sh"

SLUG="${ASDLC_SLUG:-}"
REF="${ASDLC_PR_NUMBER:-}"

bounty_report "reviser" "$SLUG" "$REF" "working"

_handler="$SCRIPT_DIR/dev-rework-handler.sh"
[ -x "$_handler" ] || _handler="${ASDLC_ROOT:?ASDLC_ROOT is required}/scripts/dev-rework-handler.sh"

if "$_handler" "$@"; then
    bounty_report "reviser" "$SLUG" "$REF" "done"
else
    _rc=$?
    bounty_report "reviser" "$SLUG" "$REF" "failed"
    exit "$_rc"
fi
