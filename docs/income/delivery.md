# Delivery runbook

Both SKUs, start to finish. The tooling does the analysis; almost all of your time
goes into access, threshold judgement, and the call.

---

## Attribution Audit — 5 business days, 6–9 hours of work

### Day 0 — Access request (send within an hour of payment)

Send this list verbatim. Naming exactly what you need, and what you explicitly don't,
closes the trust gap faster than any reassurance.

> To run the audit I need read-only access to four things:
>
> 1. **Meta Ads** — Analyst role on the ad account (view only, cannot edit)
> 2. **GA4** — Viewer on the property
> 3. **CRM** (HubSpot/Salesforce) — read-only API key or a read-only user
> 4. **Stripe** — a restricted key with read access to Charges, Customers, and Refunds
>
> I don't need: admin on anything, write access to anything, or your ad account
> password. If any of the four isn't possible, tell me which — I can still produce
> most of the report, and I'll tell you up front which sections will be empty.

**Degraded modes.** Meta + GA4 alone still yields the attribution-gap number and the
spend-to-stop list, which is the finding that sells. Without Stripe you lose revenue
figures and therefore ROAS, spend-to-add, and every dollar projection. Say so before
you start, never after.

### Day 1 — Pipeline (2 hours)

```bash
cp .env.example .env               # fill in their warehouse + provider credentials
docker compose up -d
adagent db migrate
adagent doctor                     # confirm every path reads "live", not "mock"
```

Configure `airbyte/connections.yaml` for their sources and run the first sync. Map
raw stream names onto the tables in `migrations/clickhouse/001_dimensions.sql` via
`stg_` views — this is the step that actually takes the time, and it differs per
connector version.

**One thing to check before anything else:** does `utm_content` carry an ad
identifier on their inbound sessions? If they have never stamped it, the deterministic
ad → session hop does not exist and everything falls back to lower-confidence
matching. This is not a blocker — it is a *finding*, and usually the most valuable one
in the report. Their entire measurement stack is guessing at the first hop.

### Day 2 — Sync and sanity-check (1 hour)

Let the sync complete, then:

```bash
adagent loop --dry-run             # decides, writes nothing
adagent economics --days 30        # the raw view
```

Sanity gate before you go further: **does total spend in `adagent economics` match
what Meta's own UI reports for the same window?** If it doesn't, the pipeline is
wrong, not the account. Fix it before producing anything.

### Day 3 — Tune thresholds (1–2 hours)

This is the part you are actually paid for, and the defaults in `thresholds.yaml` are
for a $60-target-CPA business. Set from their real numbers:

| Setting | How to set it |
|---|---|
| `target_cpa` | Their stated allowable CAC. Ask; don't infer. |
| `cpa_max` | ~1.5× target, or their true break-even CAC if they know it |
| `roas_min` | Break-even ROAS = 1 / gross margin. A 40% margin brand breaks even at 2.5x, not 1.2x. |
| `roas_scale` | Where they'd genuinely want to spend more, usually 1.5–2× `roas_min` |
| `attribution.lookback_days` | Their actual purchase consideration window |
| `attribution.lag_hours` | How long after a click revenue typically lands. Get this wrong and good ads look dead. |

Then re-run `adagent loop --dry-run` and read the decisions. If the report will
recommend pausing something they consider a flagship ad, know that *now* and be ready
to walk through the arithmetic on the call.

### Day 4 — Generate and review (1 hour)

```bash
adagent audit --days 30 --client "Their Company" --output their-audit.md
```

Read every line before sending. Two checks specifically:

- **Does any recommendation look absurd?** A 3x ROAS ad in "spend to stop" means the
  thresholds are wrong for their margin structure, not that the ad is bad. Go back to
  day 3.
- **Is the headline number defensible out loud?** You will be asked to justify it. If
  you cannot explain a figure from the ledger in one sentence, cut it.

Convert to PDF if they expect one. The Markdown is deliberately plain — it reads as an
engineering artifact rather than a brochure, which is the correct impression.

### Day 5 — The walkthrough (90 minutes)

Send the report **one hour before** the call, not days. You want to walk them through
it live the first time, so the framing is yours.

Order on the call:
1. The attribution gap. This reframes everything that follows.
2. Spend to stop — with the confidence-bound reasoning, not just the list.
3. Spend you cannot measure. Usually the most uncomfortable and most valuable section.
4. **Ads that look worse than they are.** Do not skip this. It proves you are
   measuring rather than cost-cutting, and it is what makes them trust the rest.
5. What you'd do next — which is the retainer, named plainly and once.

Then stop talking. The report either did the work or it didn't.

### The transition to retainer

Ask exactly one question at the end:

> The audit is a snapshot. Everything in it drifts back within about a quarter as
> creative fatigues and new ads launch. Do you want to run this yourself from the
> config I'm leaving you, or should I keep it running?

Both answers are fine. Roughly 40% take the second, and the ones who take the first
often come back a quarter later.

---

## Managed Acquisition — the weekly loop

### Onboarding (once, ~4 hours)

Pipeline is already built from the audit. Deploy per the main README's Railway
section: `adagent worker` and `adagent scheduler`, plus Railway Postgres, then
`railway run adagent db migrate`.

```bash
ADAGENT_META__DRY_RUN=true         # for the first two weeks. No exceptions.
```

In `thresholds.yaml`:

```yaml
max_actions_per_day: 10                 # start low, raise as the ledger earns it
human_approval_spend_threshold: 200.0   # you see everything meaningful first
kill_switch: false
```

### Weeks 1–2 — dry-run

The agent decides and records; nothing reaches Meta.

```bash
adagent actions --days 7
```

Read every decision against what you would have done. Send the client a short weekly
note: *"here's what it would have done, here's what I agree with, here's what I don't
and why."* This is the highest-trust artifact in the whole engagement, and it costs
you an hour.

### Going live

Flip `ADAGENT_META__DRY_RUN=false`. Keep the approval threshold low.

```bash
adagent actions --pending          # what's waiting on you
adagent approve <id>
```

Raise `human_approval_spend_threshold` and `max_actions_per_day` gradually, over
months, as the ledger accumulates decisions you agreed with. There is no reward for
rushing this.

### Every week (~4 hours per client)

| Step | Command | Time |
|---|---|---|
| Review the week's decisions | `adagent actions --days 7` | 45 min |
| Clear the approval queue | `adagent actions --pending` | 30 min |
| Check economics against expectation | `adagent economics --days 30` | 30 min |
| Confirm entropy isn't collapsing | `adagent harvest` | 15 min |
| Write the client summary | — | 45 min |
| Buffer / investigation | — | 75 min |

### Monthly

Re-run `adagent audit` and send it. It shows the trend rather than a snapshot, and it
is the single most effective retention artifact you have — the client can see the
waste line falling month over month. Re-tune thresholds against their current margin
at the same time.

### If something goes wrong

```yaml
kill_switch: true    # in thresholds.yaml — freezes all writes immediately
```

Then tell the client before they notice. Every decision is in `agent_actions` with the
exact metrics that justified it, which means a post-mortem is always possible and
always specific. Use that; it is why the ledger exists.
