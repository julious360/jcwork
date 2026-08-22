#!/usr/bin/env bash
# Weekly: every unprocessed transcript in memory/inbox/transcripts/ becomes a
# newsletter in memory/outbox/newsletters/. Idempotent — an existing output is skipped.
source "$(dirname "$0")/../lib/common.sh"
routine_start

IN="$ROOT/memory/inbox/transcripts"
OUT="$ROOT/memory/outbox/newsletters"
mkdir -p "$OUT"
processed=0

shopt -s nullglob
for f in "$IN"/*.md; do
  case "$f" in *.pains.md) continue;; esac
  slug="$(basename "${f%.md}")"
  if [[ -f "$OUT/$slug.md" ]]; then log "skip $slug (already written)"; continue; fi

  log "processing $slug"
  run_skill "/transcript-to-newsletter $f" "Read,Write,Bash(ls:*)" >/dev/null
  if [[ -f "$OUT/$slug.md" ]]; then processed=$(( processed + 1 )); else log "WARN: no output for $slug"; fi
done

python "$ROOT/os/connectors/vcc_state.py" >>"$LOG_FILE" 2>&1
routine_done "$processed newsletter(s) written"
