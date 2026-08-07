# The $5,000/week workflow

A concrete, sellable path to a $21,667/month run rate, built on the one asset that
already exists in this repository: a working attribution and ad-decision engine that
most agencies charging $8k/month do not have.

Read the honest framing first. It changes what you do on Monday.

---

## 1. What this is, and what it is not

**This agent does not generate revenue. It spends money to acquire customers for a
product.** Pointed at a Meta account with a budget, it makes that budget go further.
It is a cost-efficiency engine, not an income source. Three specific things stand
between this repo and a dollar of its own revenue:

- `agent/config/campaign.yaml` is still the worked example (`Acme Studio`). There is
  no product configured, so there is nothing to sell and no landing page to send
  traffic to.
- `ADAGENT_META__ACCESS_TIER=limited`. Production write access needs Meta App Review.
- The project's own README mandates **at least a week of dry-run** against live data
  before granting write access, and it is right to.

So "point the agent at Meta and collect $5,000/week" is not available immediately, and
would not be available quickly even with a product to sell — you would be funding ad
spend out of pocket for weeks before net revenue existed.

**What is available immediately is the capability, sold as a service.** Attribution is
a real, expensive, widely-felt problem. Every DTC brand and agency spending over
~$30k/month is optimising against a Meta dashboard that overstates conversions by
roughly half, and most of them know it and cannot fix it. You have working software
that measures the gap and quantifies what it costs. That is the product.

**Honest timeline.** First cash in 2–3 weeks. $5,000/week run rate at roughly
**90–120 days** of consistent outreach. Anyone promising you faster than that on cold
traffic is selling something. The workflow below is built to hit that, and every
assumption in it is written down so you can check it against your own results instead
of taking it on faith.

---

## 2. The arithmetic

$5,000/week = **$21,667/month**. Two SKUs get you there. Full scope and pricing in
[`offer.md`](offer.md).

| SKU | Price | Delivery effort | Role |
|---|---|---|---|
| **Attribution Audit** | $2,500 fixed | 6–9 hours, once | The wedge. Fast cash, low trust required. |
| **Managed Acquisition** | $5,500/month | ~4 hours/week | The engine. This is what gets you to $5k/week. |

Two routes to the number:

- **Retainer-led:** 4 retainers × $5,500 = **$22,000/mo**. Stable, ~16 hrs/week.
- **Mixed:** 2 retainers ($11,000) + 4 audits ($10,000) = **$21,000/mo**. Faster to
  first cash, but you re-sell it every month.

Target the mixed route first because it pays sooner, and let it convert into the
retainer-led route as audits mature into retainers.

**Capacity check.** 4 retainers (16 hrs) + 1 audit/week (8 hrs) ≈ **24 hours/week**.
This fits one person. Past 5 retainers it does not, and that is the point to raise
prices rather than hire.

### The assumptions behind the ramp

These are estimates. Written down so you can replace them with your own numbers after
four weeks — that is the entire purpose of [`pipeline.csv`](pipeline.csv).

| Assumption | Value | Where it comes from |
|---|---|---|
| Targeted outbound touches per week | 100 | What one person can do well in ~5 hrs |
| Reply rate | 8–12% | Typical for specific, researched, non-templated outreach |
| Reply → call | ~35% | |
| Call → audit sold | ~30% | The audit is cheap enough to be an easy yes |
| **Audits sold per week** | **~1** | The product of the above |
| Audit → retainer | ~40% | The report ends by naming the gap it cannot close alone |

Which produces this ramp:

| Weeks | Activity | Cumulative | Run rate |
|---|---|---|---|
| 1–2 | Build the list, ship your own sample report, start outreach | — | $0 |
| 3–4 | First 1–2 audits sold and delivered | 2 audits | ~$1,250/wk |
| 5–8 | ~4 more audits; first 1–2 retainers convert | 6 audits, 2 retainers | ~$3,300/wk |
| 9–12 | Audits continue; retainers reach 4 | 10 audits, 4 retainers | **~$5,100/wk** |

If your reply rate comes in at 4% instead of 10%, this takes twice as long. That is
the main risk, and the fix is always targeting quality, never volume.

---

## 3. The first 14 days

Everything here is doable without a single client and without spending money.

### Days 1–2 — Make the deliverable real

The audit is already built. Prove it to yourself.

```bash
docker compose up -d
adagent db migrate
adagent seed
adagent verify                       # the engine reaches the right conclusions
adagent audit --client "Demo Co" --output demo-audit.md
```

Then read [`sample-audit.md`](sample-audit.md) — a full report against a synthetic
$48k/month account. That document is your entire sales asset. You are not selling a
call, a framework, or a discovery process. You are selling *that*, filled in with
their numbers.

### Days 3–4 — Build the list

50 companies. Not 500. See [`outreach.md`](outreach.md) for the targeting filters and
where to find them. The whole approach depends on the list being narrow enough that
each message can reference something specific and true about that company.

### Days 5–7 — Ship the free version publicly

Write one post — LinkedIn, X, an industry Slack, wherever your buyers actually are —
that shows the sample report and states the finding plainly:

> Meta reported 818 conversions last month for this account. 371 could be traced to a
> payment. Here's the join that shows the difference, and what the 53% gap cost.

This is not marketing. It is proof-of-work, and it makes the cold outreach in week two
warm. Do not gate it behind an email address.

### Days 8–14 — 100 outbound touches

20 per day, 5 days. Templates and objection handling in
[`outreach.md`](outreach.md). Log every one in [`pipeline.csv`](pipeline.csv).

Expect roughly 10 replies, 3 calls, and 1 audit sold in this first batch. If you get
zero replies from 100 well-researched messages, the problem is the list, not the
message — go back to day 3.

---

## 4. The weekly operating cadence

Once running, the week has a fixed shape. Protect it; the failure mode of this
business is delivery crowding out sales until the pipeline is empty.

| Day | Block | Hours |
|---|---|---|
| Mon | **Sales.** 40 outbound touches. Update the pipeline. | 3 |
| Tue | **Delivery.** Retainer loop reviews — read `adagent actions` for each client, approve or override, send a 5-line summary. | 4 |
| Wed | **Sales.** 40 touches + every call booked this week. | 4 |
| Thu | **Delivery.** Audit production. One audit, start to finish. | 6 |
| Fri | **Delivery + admin.** Remaining retainer work, invoicing, one public post. | 4 |
| — | Buffer | 3 |

**The rule that matters:** never skip Monday or Wednesday. Delivery work always feels
more urgent than sales work and is always less important, because delivery is already
paid for and sales is not.

---

## 5. Delivering the work

Full runbook in [`delivery.md`](delivery.md). In short:

**Audit** (6–9 hours, once): they grant read-only access to Meta, GA4, CRM, and
Stripe → Airbyte syncs into ClickHouse → `adagent audit` produces the report → you
spend most of the time on the 90-minute walkthrough call, not on the document.

**Retainer** (~4 hours/week): the scheduler runs the loop against their account.
Keep `ADAGENT_META__DRY_RUN=true` for the first two weeks of every engagement, no
exceptions — that is what the ledger is for, and it is also what turns a nervous
client into a confident one. Then flip to live with
`human_approval_spend_threshold` set low, and raise it as trust builds.

The tooling does the analysis. You are paid for the judgement about thresholds, the
decision to override, and the fact that someone is accountable.

---

## 6. What can go wrong

- **You cannot get warehouse access.** Some clients will not grant Stripe or CRM
  access to a stranger. Mitigation: the audit degrades gracefully — Meta + GA4 alone
  still produces the attribution-gap number, which is the finding that sells. Say
  up front which sections will be blank without full access.
- **Delivery crowds out sales.** The single most common way this stalls at
  $2,000/week. The Monday/Wednesday rule exists for this.
- **You sell a number the account then misses.** Every projection in the audit is
  deliberately conservative — one capped budget step, net of added spend, at observed
  ROAS rather than the confidence bound. Do not inflate them in conversation.
- **Thresholds wrong for their margin structure.** The defaults in `thresholds.yaml`
  are for a $60-target-CPA business. A brand with a $40 AOV and a brand with a $4,000
  contract value need entirely different numbers. Tune them in the first call and say
  openly that the audit's calls change when you do.
- **Meta App Review.** Only needed to run *live* writes at scale. Audits and dry-run
  retainers do not require it — start the application in week one anyway, because it
  takes weeks and you will want it by month three.

---

## 7. Files here

| File | What it is |
|---|---|
| [`offer.md`](offer.md) | The two SKUs: scope, price, inclusions, exclusions, terms |
| [`outreach.md`](outreach.md) | Targeting filters, message templates, objection handling |
| [`delivery.md`](delivery.md) | The audit runbook and the retainer weekly loop |
| [`sample-audit.md`](sample-audit.md) | A complete report against a synthetic account |
| [`pipeline.csv`](pipeline.csv) | The tracker. Replace the assumptions above with facts. |

**Pipeline stages**, in order: `researched` → `touched` → `replied` → `called` →
`audit_sold` → `audit_delivered` → `retainer`, or `lost` at any point. One row per
company, not per message. Delete the three example rows before you start.
