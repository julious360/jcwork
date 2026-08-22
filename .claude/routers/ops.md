# ops.md — Ops Department

Parent: `claude.md`. Scope: it runs, it stays running, and it's the same everywhere.

## Skills

- `.claude/skills/ship-check/` — the pre-push gate (lint, format, types, tests).

## Files

| File | Purpose |
|---|---|
| `agent/orchestrator/scheduler.py` | enqueues the loop on `check_interval_hours` |
| `agent/orchestrator/worker.py` | drains the job queue |
| `agent/ops/queue.py` / `agent/ops/db.py` | Postgres-backed queue + migrations |
| `agent/ops/breaker.py` | circuit breaker around external calls |
| `agent/ops/ledger.py` | action ledger + idempotency keys |
| `docker-compose.yml` | local ClickHouse + Postgres |
| `railway.json` / `Dockerfile` | deploy |
| `.github/workflows/ci.yml` | the gate: ruff → ruff format → mypy → pytest |

## Routines

| Kind | Path | Notes |
|---|---|---|
| Local (cron) | `os/routines/local/` + `crontab.example` | laptop; sleeps when you do |
| Cloud (systemd) | `os/routines/cloud/systemd/` | VPS; 24/7 loop + worker |
| Shared memory | `os/routines/cloud/syncthing/` | one `memory/` tree across both |
| Shared helpers | `os/routines/lib/common.sh` | locking, logging, env loading |

## Commands

```bash
docker compose up -d && adagent db migrate
adagent doctor                 # which integrations are live vs mocked
adagent worker                 # drain jobs
adagent scheduler              # enqueue on interval
ruff check agent tests && ruff format --check agent tests && mypy agent && pytest -q
```

## Gotchas

- Every routine takes an `flock` lock in `common.sh`. Local and cloud must never run
  the same routine concurrently against one ledger — that's what idempotency keys are
  for, but don't rely on them as a scheduler.
- Syncthing syncs `memory/`, never `.git/` or `.env`. See the `stignore` file.
- `kill_switch: true` in `thresholds.yaml` freezes all writes without a deploy.
