#!/usr/bin/env bash
# Serve the Virtual Command Center. A server (not file://) is needed so the page can
# fetch ./data/state.json — opened directly, it falls back to sample data.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PORT="${PORT:-8787}"
cd "$ROOT"
python3 os/connectors/vcc_state.py || echo "state refresh failed — serving last known state"
echo "Virtual Command Center → http://localhost:$PORT/apps/command-center/"
exec python3 -m http.server "$PORT" --bind 127.0.0.1
