#!/usr/bin/env bash
# Every 15 minutes: rebuild apps/command-center/data/state.json.
source "$(dirname "$0")/../lib/common.sh"
routine_start
python "$ROOT/os/connectors/vcc_state.py" >>"$LOG_FILE" 2>&1
routine_done "state.json refreshed"
