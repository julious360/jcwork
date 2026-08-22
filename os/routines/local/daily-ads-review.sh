#!/usr/bin/env bash
# Daily: dry-run the decision loop, refresh the dashboard, and on Mondays write the
# weekly review. Never writes to Meta — `adagent loop --dry-run` is hardcoded here.
source "$(dirname "$0")/../lib/common.sh"
routine_start

adagent doctor >>"$LOG_FILE" 2>&1 || log "doctor reported problems"
adagent loop --dry-run >>"$LOG_FILE" 2>&1

python "$ROOT/os/connectors/vcc_state.py" >>"$LOG_FILE" 2>&1

if [[ "$(date +%u)" == "1" ]]; then
  mkdir -p "$ROOT/memory/outbox/reviews"
  run_skill "/weekly-ads-review" "Bash(adagent:*),Read,Write" \
    > "$ROOT/memory/outbox/reviews/$(date +%F)-weekly.md"
  log "weekly review written"
fi

routine_done "loop dry-run + dashboard refreshed"
