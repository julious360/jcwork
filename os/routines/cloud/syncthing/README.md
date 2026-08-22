# Syncthing — one memory across local and cloud

The cloud agent and the laptop must read the same `memory/` tree, or the dashboard
shows one machine's truth and the routines re-do each other's work. Git is the wrong
tool for this (a routine writing every 15 minutes would produce a commit storm);
Syncthing gives continuous, conflict-aware, peer-to-peer sync with no server.

## What syncs

| Path | Syncs | Why |
|---|---|---|
| `memory/inbox/` | yes | capture on the laptop, process in the cloud |
| `memory/outbox/` | yes | cloud writes it, you read it locally |
| `memory/logs/*.status.json` | yes | routine health for the dashboard |
| `memory/logs/*.log` | no | noisy, per-host, rotated |
| `.git/`, `.venv/`, `.env` | **never** | credentials and per-host state |
| `agent/config/*.yaml` | optional | syncing it makes `kill_switch` instant everywhere |

## Install

```bash
# both hosts
curl -fsSL https://syncthing.net/release-key.gpg | gpg --dearmor -o /usr/share/keyrings/syncthing.gpg
echo "deb [signed-by=/usr/share/keyrings/syncthing.gpg] https://apt.syncthing.net/ syncthing stable" \
  > /etc/apt/sources.list.d/syncthing.list
apt-get update && apt-get install -y syncthing

# cloud (headless, as the agent user)
systemctl enable --now syncthing@agent
ssh -L 8384:127.0.0.1:8384 agent@vps    # then open http://localhost:8384
```

## Configure

1. Add the other host by Device ID (Actions → Show ID on each).
2. Add folder — Folder Path `/srv/jcwork/memory` (cloud) ↔ `~/jcwork/memory` (laptop),
   Folder ID `jcwork-memory` on **both**. A mismatched ID is the usual reason a folder
   silently never syncs.
3. Folder type: **Send & Receive** on both.
4. File Versioning: *Staggered*, 30 days. Cheap insurance against a routine that
   deletes a transcript.
5. Ignore Patterns: paste `stignore.example` (below) into the folder's Ignore Patterns.
6. Advanced → *Watch for Changes* on, `fsWatcherDelayS` 10. Sub-minute propagation
   without polling the tree.

## Conflicts

Syncthing writes `<name>.sync-conflict-<date>-<device>.md` rather than choosing.
`memory/outbox/` is append-only by convention (dated filenames), so real conflicts
should only appear if the same routine ran on both hosts — which is what the `flock`
lock and the one-authoritative-host rule exist to prevent. If you see one, that rule
was broken; fix the schedule, don't just delete the file.

```bash
find memory -name '*.sync-conflict-*' -mmin -1440
```

## Sanity check

```bash
date -u +%FT%TZ > memory/logs/sync-probe.txt   # laptop
cat memory/logs/sync-probe.txt                 # cloud, within ~15s
```
