# ads.md — Ads Department

Parent: `claude.md`. Scope: what runs, what gets paused, what gets scaled.

## Skills (try these before reading code)

- `.claude/skills/ad-concept-brief/` — pain point → brand-safe concept brief + copy.
- `.claude/skills/weekly-ads-review/` — ledger + economics → HTML review.

## Files

| File | What it decides |
|---|---|
| `agent/decision/rules.py` | pause / scale / hold, from CPA + ROAS |
| `agent/decision/guardrails.py` | sample-size floor, learning phase, blast radius, kill switch |
| `agent/decision/statistics.py` | confidence bounds — rules act on bounds, not point estimates |
| `agent/decision/engine.py` | orchestrates rules → guardrails → ledger |
| `agent/creative/pipeline.py` | concept → copy → image/video → validation |
| `agent/creative/brand_validator.py` | deterministic pixel/spec checks, then vision judgement |
| `agent/entropy/novelty.py` | rejects concepts too similar to recent shipped work |
| `agent/entropy/sources.py` | external DNA (Ad Library, YouTube, podcasts) |
| `agent/meta/write_client.py` | **write-only** Meta client |
| `agent/meta/rate_governor.py` | points budget: reads 1, writes 3 |

## Config (edit these, not the code)

- `agent/config/thresholds.yaml` — `target_cpa`, `cpa_max`, `roas_min`, `roas_scale`,
  guardrails, blast radius, `kill_switch`, novelty, attribution lag.
- `agent/config/campaign.yaml` — vertical, ICP, research seeds, entropy sources.
- `agent/config/brand_guide.yaml` — palette, ΔE tolerance, aspect ratios, forbidden claims.

## Commands

```bash
adagent config                 # active thresholds + guardrails
adagent research               # ranked pain points (JSON)
adagent creative               # generate + brand-validate candidates
adagent loop --dry-run         # decide against real data, write nothing
adagent actions --limit 20     # the ledger: what it decided, and why
adagent approve <action_id>    # release an action above the approval threshold
```

## Gotchas

- A pause that "should have fired" is usually a guardrail, not a bug: check
  `min_spend_multiple`, `min_impressions`, and `attribution.lag_hours` first.
- Revenue lands late. Anything inside the 48h lag window is deliberately excluded.
- Never add a read path to Meta to "just check" — query the warehouse instead.
