# claude.md — Workspace Router

**Read this file first, then load exactly one sub-router.** Nothing else in this
workspace should be searched blind. If a task does not map to a department below,
say so instead of grepping the tree.

Workspace: `~/jcwork` · Product: `adagent` (autonomous Meta Ads agent) · Runtime: Python 3.11+

## Departments

| Department | Sub-router | Owns | Load when the ask is about |
|---|---|---|---|
| Ads | `.claude/routers/ads.md` | decision loop, creative, entropy, Meta writes | pausing/scaling ads, CPA/ROAS, creative generation, guardrails |
| Content | `.claude/routers/content.md` | transcripts, newsletters, ad copy voice | newsletters, transcripts, long-form → short-form, copy tone |
| Finance | `.claude/routers/finance.md` | spend, attributed revenue, unit economics | budget, burn, CAC/LTV, refunds, "is this profitable" |
| Ops | `.claude/routers/ops.md` | migrations, workers, CI, deploy, routines | infra, cron/systemd, sync, failing builds, releases |

## Routing rules

1. One hop. `claude.md` → one sub-router → the files that sub-router names. Do not
   open a third router "for context".
2. Sub-routers list **skills first, reference files second**. If a skill covers the
   task, invoke the skill and stop reading.
3. Anything not listed in a sub-router is out of working memory by design. To make a
   file reachable, add a line to the sub-router — do not deepen the folder tree.
4. Generated/derived state (`apps/command-center/data/state.json`, `memory/logs/*`)
   is never authoritative. Regenerate it; don't reason from a stale copy.

## Skill index (A of ARMS lives in `apps/`, S lives here)

| Skill | Path | Headless trigger |
|---|---|---|
| `ad-concept-brief` | `.claude/skills/ad-concept-brief/` | `claude -p "/ad-concept-brief <pain-point>"` |
| `transcript-to-newsletter` | `.claude/skills/transcript-to-newsletter/` | `claude -p "/transcript-to-newsletter <file.md>"` |
| `weekly-ads-review` | `.claude/skills/weekly-ads-review/` | `claude -p "/weekly-ads-review"` |
| `ship-check` | `.claude/skills/ship-check/` | `claude -p "/ship-check"` |

## Routines (R)

| Routine | Where | Cadence | Script |
|---|---|---|---|
| Daily ads review | local cron | 08:00 daily | `os/routines/local/daily-ads-review.sh` |
| Weekly newsletter | local cron | Mon 07:00 | `os/routines/local/weekly-newsletter.sh` |
| Dashboard state refresh | local cron | every 15 min | `os/connectors/vcc_state.py` |
| Loop + worker | cloud (VPS) | continuous | `os/routines/cloud/systemd/` |

Cloud and local share one memory tree via Syncthing — see `os/routines/cloud/syncthing/README.md`.

## Applications (A)

| App | Path | Run |
|---|---|---|
| Virtual Command Center | `apps/command-center/index.html` | `./apps/command-center/serve.sh` → http://localhost:8787 |
| Dashboard state connector | `os/connectors/vcc_state.py` | `python os/connectors/vcc_state.py` |
| YouTube transcript connector | `os/connectors/youtube_transcript.py` | `python os/connectors/youtube_transcript.py <url>` |

## Invariants (violating these breaks the build)

- **The Meta client is write-only.** No read/GET method may be added to
  `agent/meta/write_client.py`; `tests/test_meta_write_only.py` enforces it.
- **`ADAGENT_META__DRY_RUN` defaults to true.** Never flip it in code, config
  defaults, or a routine. It is an operator decision, made in `.env`.
- **Decisions are made against `mart_ad_economics`**, not Meta-reported conversions.
- **Every mutation goes through `ActionLedger`** with an idempotency key claimed
  before the API call.
- CI gate: `ruff check agent tests && ruff format --check agent tests && mypy agent && pytest`.

## Memory tree

```
memory/inbox/transcripts/    raw captured input (transcripts, exports)
memory/outbox/newsletters/   finished artifacts, dated
memory/logs/                 routine run logs (gitignored)
```
