# Cloud routines — 24/7 agent on a VPS

Local cron dies when the laptop sleeps. Anything that must not miss a window — the
decision loop, the worker, the daily review — belongs here. The same scripts run in
both places; only the scheduler differs (cron vs systemd timers).

## Split

| Runs where | What | Why |
|---|---|---|
| Cloud | `adagent worker`, `adagent scheduler`, daily review, newsletter | must not miss a window |
| Local | ad-hoc skills, dashboard refresh, anything interactive | you're at the keyboard |
| Both | reads of `memory/` | Syncthing keeps one tree |

**Only one host runs write-capable routines.** Two schedulers against one ledger will
race; idempotency keys make that survivable, not correct. Keep the cloud authoritative.

## Provision (Ubuntu 22.04+, 2 vCPU / 4 GB minimum)

```bash
adduser --system --group --home /srv/jcwork agent
apt-get update && apt-get install -y python3.12-venv git curl flock

git clone git@github.com:julious360/jcwork.git /srv/jcwork
cd /srv/jcwork
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

cp .env.example .env && chmod 600 .env && chown agent:agent .env
#   set ADAGENT_ENVIRONMENT=production
#   leave ADAGENT_META__DRY_RUN=true until the ledger has been read for a week

# Claude Code, for the headless skill routines
curl -fsSL https://claude.ai/install.sh | bash    # then: claude setup-token
```

Postgres and ClickHouse: managed instances, or `docker compose up -d` on the same box
for a single-tenant setup. Then `.venv/bin/adagent db migrate` and
`.venv/bin/adagent doctor`.

## Install the units

```bash
cp os/routines/cloud/systemd/*.service os/routines/cloud/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now adagent-worker adagent-scheduler
systemctl enable --now jcwork-daily-review.timer jcwork-newsletter.timer
systemctl list-timers | grep jcwork          # next fire times
journalctl -u adagent-worker -f              # live
```

`Persistent=true` replays a timer the box missed while it was down — the property
cron does not have, and the reason the daily review is a timer and not a cron line.

## Headless auth

`claude setup-token` writes a long-lived token for non-interactive use. Store it as
root-owned `/etc/jcwork/claude.env` (mode 600) and add
`EnvironmentFile=/etc/jcwork/claude.env` to the two oneshot units. Never commit it,
and never put it in `.env` — that file syncs.

## Kill switch

`kill_switch: true` in `agent/config/thresholds.yaml` freezes every write without a
deploy. It syncs, so setting it locally stops the cloud agent within one sync cycle.
Verify with `journalctl -u adagent-worker | tail`.

## Health

`memory/logs/<routine>.status.json` is written by every routine (`status_write` in
`os/routines/lib/common.sh`) and is what the Virtual Command Center reads. Because
`memory/` syncs, the local dashboard shows cloud routine health with no API between
them — the sync *is* the transport.
