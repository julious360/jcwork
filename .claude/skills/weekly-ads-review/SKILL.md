---
name: weekly-ads-review
description: Produce the weekly ads review — economics, the decision ledger, the approval queue, and what to change — as Markdown plus a standalone HTML report. Use for weekly reviews, "how did ads do", performance summaries, or the Monday report.
---

# Weekly Ads Review

Output: `memory/outbox/reviews/YYYY-MM-DD-weekly.{md,html}`.
The HTML is rendered from `references/report.template.html` and must open with no
network access — it is emailed and archived.

## Data collection (in this order, do not skip)

```bash
adagent doctor                 # note which integrations are mocked — label the report if so
adagent config                 # thresholds in force this week
adagent economics --days 7     # spend, attributed revenue, CPA, ROAS
adagent economics --days 28    # trend baseline
adagent actions --limit 100    # what it decided, and why
```

If `doctor` reports mocked providers, the report header says **MOCK DATA** and no
recommendation is presented as actionable.

## Rules for the numbers

- Exclude the trailing `attribution.lag_hours` (48h). Say so under the headline number.
- Quote ROAS/CPA with the confidence bound the decision engine used, not just the
  point estimate: "CPA $71 (90% upper bound $88, under cpa_max $90)".
- Revenue is net of refunds, `last_non_direct_click`, 7-day lookback. State the model once.
- Any ad with spend < 3 × `target_cpa` goes in "Not yet judgeable", never in winners
  or losers.

## Sections

1. **Headline** — spend, attributed revenue, blended ROAS, Δ vs prior 7 days.
2. **Decisions taken** — from the ledger: paused, scaled, created. Each with the
   metric that triggered it. Group by `action_type`.
3. **Awaiting approval** — every `awaiting_approval` row, with its spend impact and
   the exact `adagent approve <id>` command. This is the section the operator acts on.
4. **Not yet judgeable** — under the sample-size floor; how much more spend is needed.
5. **Entropy check** — share of spend on externally-seeded concepts vs
   `exploration_pct` (20%). Under target means the account is converging on itself;
   say it plainly and name `adagent harvest`.
6. **One recommendation** — a single threshold or config change, with the number it
   should move to and why. Not a list.

## Self-check

- [ ] Every figure traces to a command whose output is quoted in the appendix
- [ ] Attribution model + lag stated once, near the top
- [ ] Approval queue lists real ledger ids
- [ ] Exactly one recommendation
- [ ] HTML opens offline, prints to one or two pages, readable in light and dark

## Headless

```bash
claude -p "/weekly-ads-review" --allowedTools "Bash(adagent:*),Read,Write" \
  --output-format text >> memory/logs/weekly-ads-review.log
```
Scheduled by `os/routines/local/daily-ads-review.sh` (weekly variant) and by the
cloud timer in `os/routines/cloud/systemd/`.
