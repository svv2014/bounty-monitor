#!/usr/bin/env bash
# merger.sh — merge-handler.sh with bounty reporting; triggers judge on merge.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/bounty.sh
source "$SCRIPT_DIR/lib/bounty.sh"

SLUG="${ASDLC_SLUG:-}"
REF="${ASDLC_PR_NUMBER:-}"

bounty_report "merger" "$SLUG" "$REF" "working"

_handler="$SCRIPT_DIR/merge-handler.sh"
[ -x "$_handler" ] || _handler="${ASDLC_ROOT:?ASDLC_ROOT is required}/scripts/merge-handler.sh"

if "$_handler" "$@"; then
    bounty_report "merger" "$SLUG" "$REF" "done" "true"
else
    _rc=$?
    bounty_report "merger" "$SLUG" "$REF" "failed"
    exit "$_rc"
fi
