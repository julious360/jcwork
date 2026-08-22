#!/usr/bin/env bash
# Shared plumbing for every routine, local and cloud.
# Source it, don't copy it:  source "$(dirname "$0")/../lib/common.sh"
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LOG_DIR="$ROOT/memory/logs"
LOCK_DIR="${XDG_RUNTIME_DIR:-/tmp}/jcwork-routines"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
mkdir -p "$LOG_DIR" "$LOCK_DIR"

ROUTINE_NAME="$(basename "${0%.sh}")"
LOG_FILE="$LOG_DIR/$ROUTINE_NAME.log"

log() { printf '%s [%s] %s\n' "$(date -u +%FT%TZ)" "$ROUTINE_NAME" "$*" >>"$LOG_FILE"; }

# Machine-readable run record — this is what the dashboard reads.
status_write() { # status_write <ok|fail|running> <message>
  local f="$LOG_DIR/$ROUTINE_NAME.status.json"
  printf '{"routine":"%s","status":"%s","at":"%s","host":"%s","message":"%s"}\n' \
    "$ROUTINE_NAME" "$1" "$(date -u +%FT%TZ)" "$(hostname -s)" "${2//\"/\'}" >"$f"
}

# One instance per routine per host. Local and cloud must not run the same routine
# concurrently against one ledger.
acquire_lock() {
  exec 9>"$LOCK_DIR/$ROUTINE_NAME.lock"
  if ! flock -n 9; then
    log "already running, exiting"
    exit 0
  fi
}

load_env() {
  if [[ -f "$ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT/.env"
    set +a
  fi
  if [[ -f "$ROOT/.venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$ROOT/.venv/bin/activate"
  fi
}

# Headless Claude. Every routine goes through here so the tool allowlist is one
# decision made in one place.
run_skill() { # run_skill "<prompt>" "<allowed-tools>"
  local prompt="$1" tools="${2:-Read,Write,Bash(adagent:*)}"
  log "skill: $prompt"
  "$CLAUDE_BIN" -p "$prompt" \
    --allowedTools "$tools" \
    --output-format text \
    2>>"$LOG_FILE"
}

# Trim logs so an unattended box never fills its disk.
rotate_logs() {
  local max_bytes=$(( 5 * 1024 * 1024 ))
  [[ -f "$LOG_FILE" ]] || return 0
  local size; size=$(wc -c <"$LOG_FILE")
  (( size > max_bytes )) && { tail -c $(( max_bytes / 2 )) "$LOG_FILE" >"$LOG_FILE.tmp"; mv "$LOG_FILE.tmp" "$LOG_FILE"; }
  return 0
}

on_error() { local code=$?; log "FAILED (exit $code) at line ${BASH_LINENO[0]}"; status_write fail "exit $code"; exit "$code"; }
trap on_error ERR

routine_start() { acquire_lock; rotate_logs; load_env; cd "$ROOT"; status_write running "started"; log "start"; }
routine_done()  { status_write ok "${1:-completed}"; log "done: ${1:-completed}"; }
