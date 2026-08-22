# Routines

Recurring work, scheduled. Scripts are shared; only the scheduler differs.

```
os/routines/
├── lib/common.sh          locking, logging, env, headless-Claude wrapper
├── local/                 cron on your machine  (+ crontab.example)
└── cloud/                 systemd on a VPS      (+ syncthing/ for shared memory)
```

## Contract every routine follows

```bash
source "$(dirname "$0")/../lib/common.sh"
routine_start        # flock, rotate logs, load .env + venv, cd to repo root, status=running
... work ...
routine_done "what happened"   # status=ok
```

- `flock` — one instance per routine per host.
- `memory/logs/<routine>.log` — human trail, auto-trimmed at 5 MB.
- `memory/logs/<routine>.status.json` — machine state; the Virtual Command Center
  reads exactly this and nothing else.
- ERR trap — any failure writes `status=fail` with the exit code before exiting.
- Headless Claude goes through `run_skill`, so the tool allowlist is one decision in
  one place rather than scattered across scripts.

## Adding one

1. Write the script in `local/`, source `common.sh`, use `routine_start` / `routine_done`.
2. `chmod +x`, add a line to `local/crontab.example`.
3. If it must not miss a window, add a `.service` + `.timer` pair in `cloud/systemd/`
   (`Persistent=true`).
4. Add the row to the Routines table in `claude.md` — otherwise the agent can't see it.

## Local vs cloud, decided

| Question | Answer |
|---|---|
| Must it run at a fixed time even if the laptop is shut? | cloud timer |
| Does it write to Meta or the ledger? | cloud only, one host |
| Does it need your keyboard, screen, or local files? | local cron |
| Does it just read `memory/`? | either — Syncthing makes them the same |
