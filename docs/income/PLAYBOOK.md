# The $5,000/week playbook

One file, read top to bottom in about twenty minutes. It is self-contained — the other
documents in this folder are the same material split by topic, and you do not need
them to follow this.

Its purpose is to let you **decide what to work on**, so section 3 is a decision board
rather than a plan you are expected to execute in order. Sections 1 and 2 are the
context that makes that decision sane. Everything after section 3 is reference detail
for whichever track you pick.

---

## 1. The honest framing

**This agent does not generate revenue. It spends money to acquire customers for a
product.** Pointed at a Meta account with a budget, it makes that budget go further.
It is a cost-efficiency engine, not an income source.

Three specific things stand between this repository and a dollar of its own revenue:

- `agent/config/campaign.yaml` is still the worked example (`Acme Studio`). There is no
  product configured, so there is nothing to sell and no landing page to send traffic
  to.
- `ADAGENT_META__ACCESS_TIER=limited`. Production write access requires Meta App
  Review, which takes weeks.
- The project's own README mandates **at least a week of dry-run** against live data
  before granting write access, and it is right to.

So "point the agent at Meta and collect $5,000/week" is not available immediately, and
would not be available quickly even with a product to sell — you would be funding ad
spend out of pocket for weeks before net revenue existed.

**What is available immediately is the capability, sold as a service.** Attribution is
a real, expensive, widely-felt problem. Most brands spending over ~$30k/month are
optimising against a Meta dashboard that overstates conversions by roughly half, and
many of them know it and cannot fix it. You have working software that measures the gap
and quantifies what it costs. That is the product.

**Honest timeline.** First cash in 2–3 weeks. A $5,000/week run rate at roughly
**90–120 days** of consistent outreach. Anyone promising faster than that on cold
traffic is selling something. Every assumption behind those numbers is written down in
section 10 so you can check it against your own results rather than taking it on faith.

---

## 2. The arithmetic

$5,000/week = **$21,667/month**. Two SKUs get you there.

| SKU | Price | Delivery effort | Role |
|---|---|---|---|
| **Attribution Audit** | $2,500 fixed | 6–9 hours, once | The wedge. Fast cash, low trust required. |
| **Managed Acquisition** | $5,500/month | ~4 hours/week | The engine. This is what reaches $5k/week. |

Two routes to the number:

- **Retainer-led:** 4 retainers × $5,500 = **$22,000/mo**. Stable, ~16 hrs/week.
- **Mixed:** 2 retainers ($11,000) + 4 audits ($10,000) = **$21,000/mo**. Faster to
  first cash, but you re-sell it every month.

Target the mixed route first because it pays sooner, and let it convert into the
retainer-led route as audits mature into retainers.

**Capacity check.** 4 retainers (16 hrs) + 1 audit/week (8 hrs) ≈ **24 hours/week**.
That fits one person. Past 5 retainers it does not, and that is the point to raise
prices rather than hire.

---

## 3. What to work on

The critical path to first cash is short. Most of the engineering in this repository is
already done, and most of what remains is not on the path.

### The critical path

```
A1 verify it runs  ──►  B1 publish the proof  ──►  B2 build the list  ──►  C1 outreach
   (30 min)                  (3 hours)                  (1 day)             (ongoing)
```

Four items. Nothing else is required to sell the first audit. If you do only these, you
are on the timeline in section 1.

### Everything, with honest effort and sequencing

| # | Item | Effort | When it matters | On critical path |
|---|---|---|---|---|
| **A1** | Run the warehouse path locally: `docker compose up -d && adagent db migrate && adagent seed && adagent audit` | 30 min | Now. You cannot sell a report you have never watched run. | **Yes** |
| **A2** | `adagent audit --demo` — render a sample with no databases | 2 hrs | Before your first live call, so you can demo from any machine | No |
| **A3** | PDF export of the report | 3 hrs | First buyer who asks for one. Not before. | No |
| **A4** | Point `campaign.yaml` at a real product of your own | days–weeks | Only if you want to run ads for yourself. Not part of this business. | No |
| **B1** | Publish the sample report publicly as proof-of-work | 3 hrs | Now. It converts cold outreach into warm. | **Yes** |
| **B2** | Build the 50-company list (section 6) | 1 day | Now. The single highest-leverage item here. | **Yes** |
| **B3** | Load the outreach sequence into a real sending tool | 2 hrs | Around touch 100, when manual sending starts to hurt | No |
| **C1** | 100 researched outbound touches | ~5 hrs/wk | Continuously, from week 2 | **Yes** |
| **C2** | Run calls, sell the first audit | ~2 hrs/wk | From week 3 | **Yes** |
| **D1** | Start Meta App Review | 2 hrs to file | File in week 1 — it takes weeks and you want it by month 3 | No |
| **D2** | Railway deploy (`worker` + `scheduler`) | 3 hrs | At your **first retainer**, not before | No |
| **D3** | Airbyte stream mapping for a client's stack | 2–4 hrs | At your **first paying client**, per client | No |

### How to read that table

**A1 is genuinely blocking.** Not for technical reasons — the tests pass and the logic
is verified — but because the first call will include a question you can only answer
from having watched the thing run against a real warehouse.

**B2 is where the leverage is.** The difference between a 1% and a 10% reply rate is
list quality, not message quality. It is a full day of unglamorous work and it
determines whether the following 90 days work at all.

**D1 is the one thing worth starting early even though it is not on the path.** App
Review is calendar time you cannot compress, and you will want write access by the time
your third retainer lands.

**A4 is a different business.** Configuring the agent for your own product means buying
your own traffic, which requires a product, a landing page, and weeks of funded spend
before net revenue. It is not a faster path to $5k/week; it is a slower one with more
capital at risk. Listed only so the decision is explicit rather than accidental.

### If you have limited time this week

- **Two hours:** A1, then read the sample report end to end.
- **A day:** A1 + B1.
- **A week:** the whole critical path, ending with the first 40 touches sent.

---

## 4. The offer

Two SKUs. Resist adding a third — this sells because the buyer understands it in one
sentence.

### SKU 1 — Attribution Audit · $2,500 fixed · 5 business days

> I'll show you how much of your Meta spend last month produced revenue you can trace
> to a bank deposit, and how much didn't. Fixed price, five days, and you keep the
> report whether or not we work together again.

**They get:** the written report — blended ROAS and CPA computed from settled payments
rather than platform-reported conversions; the attribution gap; spend to stop; spend to
add; spend that cannot currently be measured; and ads that look worse than they are.
Plus a recorded 90-minute walkthrough and the tuned threshold config, which they keep.

**It costs you** 6–9 hours, most of it waiting on data syncs.

**Why $2,500:** below the threshold where procurement gets involved, above the
threshold where the buyer treats it as disposable. Roughly one week of a mid-size
account's ad spend — trivially justifiable if the report finds anything at all, and on
the sample account it found $18,660/month.

**Explicitly not included:** any change to their ad account (this is read-only — say so
early and often, it removes the largest objection before it is raised), creative
production, funnel work, or ongoing monitoring.

### SKU 2 — Managed Acquisition · $5,500/month · 3-month minimum, then monthly

> The audit tells you what's wrong once. This keeps it from drifting back — the loop
> runs every 6 hours against real revenue, and a human reads every decision before it
> lands.

**They get:** the decision loop running continuously against real attributed revenue;
**two weeks of dry-run at the start of every engagement, no exceptions**; then live with
`human_approval_spend_threshold` set low and raised only as the ledger earns it; a
weekly written summary; a monthly threshold review; and the warehouse maintained.

**It costs you** ~4 hours/week per client, mostly reviewing the ledger and writing the
summary.

**Why $5,500:** below a full-time hire, below most agency retainers, and defensible
against a single number — recovering $8k/month of wasted spend on a $50k/month account
pays for itself 1.5× before any upside from scaling winners.

### Terms worth holding

- **Payment.** Audit 100% up front; retainer monthly in advance. You are one person;
  you do not extend credit.
- **Never guarantee ROAS.** You control spend allocation, not the market, the offer, or
  the product. Guarantee this instead: *"if the audit finds less than $2,500/month in
  recoverable spend, you don't pay."* You control it, it is honest, and it closes deals.
  The audit's built-in conservatism is what makes it safe to offer.
- **Read-only until proven.** Both SKUs start without write access to anything. This is
  the strongest trust asset you have — use it in the pitch, not just the contract.
- **Scope creep.** The moment a client asks for creative, landing pages, or email, it is
  a separate quote. Write it into the agreement so the conversation is already had.
- **Raise prices at 5 clients.** Capacity runs out around 5 retainers. Go to $7,500 for
  new clients rather than hiring.

---

## 5. The first 14 days

All of this is doable without a single client and without spending money.

**Days 1–2 — make the deliverable real.** Item A1. Run it, then read the output as a
buyer would:

```bash
docker compose up -d
adagent db migrate
adagent seed
adagent verify                       # the engine reaches the right four conclusions
adagent audit --client "Demo Co" --output demo-audit.md
```

The seeded account produces a 62.5% attribution gap — 24 platform-reported conversions
per day against 9 traceable to a settled payment. That is the shape of the finding you
are selling.

**Days 3–4 — build the list.** 50 companies, not 500. Filters in section 6. The whole
approach depends on the list being narrow enough that every message can reference
something specific and true.

**Days 5–7 — ship the free version publicly.** One post, wherever your buyers actually
are, showing the sample report and stating the finding plainly:

> Meta reported 876 conversions last month for this account. 410 could be traced to a
> payment. Here's the join that shows the difference, and what the 53% gap cost.

This is proof-of-work, not marketing, and it is what makes week two's cold outreach
warm. Do not gate it behind an email address.

**Days 8–14 — 100 outbound touches.** 20 per day, 5 days. Log every one in
`pipeline.csv`. Expect roughly 10 replies, 3 calls, 1 audit sold. If you get zero
replies from 100 well-researched messages, the problem is the list, not the message —
go back to day 3.

---

## 6. Finding buyers

### Who to target — three filters, all of which must hold

1. **Spending $30k–$250k/month on Meta.** Below $30k the audit is hard to justify
   against their budget. Above $250k they have an in-house team and a procurement
   process, and the sales cycle stops being five days.
2. **Sells something with a traceable payment** — DTC on Shopify/Stripe, or B2B SaaS
   with a CRM. If money changes hands offline, the identity spine has nothing to join
   on and you cannot deliver.
3. **Has a revenue lag.** Subscription, high-consideration, or long sales cycle. This is
   the sharpest filter: lag is precisely what makes platform-reported conversions
   diverge from banked revenue, so these accounts have the largest gap and feel it most.

### Where to find them

- **Meta Ad Library.** Filter by category, sort by ads running longest. An advertiser
  running the same creative for 90+ days is spending real money and is not iterating —
  exactly the profile with a measurement problem.
- **Shopify app store reviews** for attribution tools (Triple Whale, Northbeam, Hyros).
  Reviewers describing what still doesn't work are pre-qualified: they know they have
  the problem and have already paid to try to solve it.
- **Agencies, not just brands.** A 10-client agency is one relationship that can become
  several. Sell them the audit as something they white-label. Highest-leverage channel
  available to you.
- **Job boards.** A company hiring a "Growth Analyst — attribution" has budget and an
  admitted problem. Do not apply. Offer the audit to the hiring manager.

**Disqualify fast:** lead-gen with an offline close, anything under $30k/month, and
anyone who says "we're happy with our Meta reporting." The last is not a prospect to
educate; it is a prospect to skip.

### The messages

Three rules: **name a specific observation about them**, **make one ask**, **never
attach anything on the first touch**.

**Cold email — first touch**

> Subject: 410 of 876
>
> Hi {name} — I pulled {company} in the Meta Ad Library and you've had the {specific
> creative} running since {month}, which usually means it's working.
>
> Quick question about how you're measuring that. On most accounts I look at, Meta
> reports roughly twice the conversions that can actually be traced through to a
> payment — view-through and modelled conversions the platform counts and your bank
> account doesn't. On a synthetic $48k/month account I ran last week the gap was 53%,
> and about $18k/month of spend was sitting on the wrong side of it.
>
> I'm not going to guess at yours. Worth 15 minutes to find out?

It works because it opens with proof you looked, states a specific checkable claim, and
asks for time rather than a sale.

**Follow-up — four days later**

> Following up with the thing itself rather than a description of it — here's a full
> report against a synthetic account so you can see exactly what you'd get: {link}
>
> The part most people go to first is the section on spend you cannot currently
> measure. That's usually the number that decides whether this is worth your time.
>
> Read-only access, nothing touches the account.

**To an agency**

> {name} — you're running paid social for {N} clients. How are you handling the fact
> that Meta's reported conversions and your clients' actual revenue don't reconcile?
>
> I've built the join that closes it — ad → session → CRM → Stripe, revenue credited to
> click date, net of refunds. I sell it as a $2.5k audit, and a few agencies white-label
> it as their own quarterly deliverable.

### The call — 30 minutes

1. **(5 min)** What do you optimise against today? Let them say "Meta's dashboard."
   Correct nothing yet.
2. **(5 min)** Have you reconciled that to Stripe? Almost always no. This is the moment
   the problem becomes theirs rather than yours.
3. **(10 min)** Walk the sample report. Attribution gap first, then spend-to-stop, then
   — importantly — *ads that look worse than they are*. That section proves you are not
   another dashboard salesman telling them to cut spend.
4. **(5 min)** Scope and price. $2,500, five days, read-only, and if it finds less than
   $2,500/month recoverable they don't pay.
5. **(5 min)** Access. Name exactly what you need, in writing the same day.

**Do not do a custom analysis before they pay.** The sample report is the free version.

### Objections

**"We already use Triple Whale / Northbeam / Hyros."**
> Good — then you already believe the platform numbers are wrong. Those tools model the
> gap. This one joins through to the actual payment and tells you the confidence of
> every match, so you can see which conclusions are load-bearing. If they agree, that's
> worth knowing too.

**"Can't my agency do this?"**
> They can tell you what Meta reported. The question is whether they can tell you what
> Stripe settled, credited back to the click date and net of refunds. Ask them — the
> answer is informative either way.

**"$2,500 is a lot for a report."**
> It's about a week of your ad spend. If it finds nothing worth $2,500/month you don't
> pay. On the sample account it found $18,660/month — I'd rather show you a small number
> honestly than a big one I made up.

**"I don't want anyone touching my ad account."**
> Nothing touches it. The audit is read-only, and even the ongoing service runs two
> weeks in dry-run first — it records every decision it would have made without making
> any, and you read the log before granting write access. That's the default, not a
> concession.

**"We're too small."**
> Probably true under $30k/month — the recoverable spend won't cover the fee, and I'd
> rather say that now. Worth revisiting when you're past it.

Say the last one when it is true. Turning away a bad fit costs one deal and buys a
referral more often than not.

---

## 7. Delivering the work

### Attribution Audit — 5 business days, 6–9 hours

**Day 0 — access request, within an hour of payment.** Send the list verbatim; naming
exactly what you need and what you explicitly don't closes the trust gap faster than any
reassurance.

> Read-only access to four things: **Meta Ads** (Analyst role), **GA4** (Viewer),
> **CRM** (read-only key or user), **Stripe** (restricted key: Charges, Customers,
> Refunds). I don't need admin on anything, write access to anything, or your ad account
> password. If any of the four isn't possible, tell me which — I can still produce most
> of the report, and I'll tell you up front which sections will be empty.

**Degraded modes matter commercially.** Meta + GA4 alone still yields the
attribution-gap number and the spend-to-stop list, which is the finding that sells.
Without Stripe you lose revenue figures and therefore ROAS, spend-to-add, and every
dollar projection. Say so before you start, never after.

**Day 1 — pipeline (2 hrs).** Fill `.env` with their credentials, `docker compose up -d`,
`adagent db migrate`, `adagent doctor` until every path reads *live* rather than *mock*.
Configure `airbyte/connections.yaml` and map raw stream names onto the tables in
`migrations/clickhouse/001_dimensions.sql` via `stg_` views. This is the step that
actually takes the time and it differs per connector version.

> **Check before anything else:** does `utm_content` carry an ad identifier on their
> inbound sessions? If they have never stamped it, the deterministic ad → session hop
> does not exist and everything falls back to lower-confidence matching. This is not a
> blocker — it is a *finding*, and usually the most valuable one in the report. Their
> entire measurement stack is guessing at the first hop.

**Day 2 — sync and sanity-check (1 hr).** `adagent loop --dry-run`, then
`adagent economics --days 30`. Gate: **does total spend match what Meta's own UI reports
for the same window?** If not, the pipeline is wrong, not the account. Fix it before
producing anything.

**Day 3 — tune thresholds (1–2 hrs).** This is what you are actually paid for. The
defaults are for a $60-target-CPA business.

| Setting | How to set it |
|---|---|
| `target_cpa` | Their stated allowable CAC. Ask; don't infer. |
| `cpa_max` | ~1.5× target, or their true break-even CAC if they know it |
| `roas_min` | Break-even ROAS = 1 / gross margin. A 40%-margin brand breaks even at 2.5×, not 1.2×. |
| `roas_scale` | Where they'd genuinely want to spend more — usually 1.5–2× `roas_min` |
| `attribution.lookback_days` | Their actual purchase consideration window |
| `attribution.lag_hours` | How long after a click revenue typically lands. Get this wrong and good ads look dead. |

Re-run `adagent loop --dry-run` and read the decisions. If the report will recommend
pausing something they consider a flagship ad, know that *now* and be ready to walk
through the arithmetic.

**Day 4 — generate and review (1 hr).** `adagent audit --days 30 --client "Their
Company" --output their-audit.md`. Read every line. Two checks: does any recommendation
look absurd (a 3× ROAS ad in *spend to stop* means the thresholds are wrong for their
margin structure, not that the ad is bad — go back to day 3), and is the headline number
defensible out loud (if you cannot explain a figure from the ledger in one sentence, cut
it).

**Day 5 — the walkthrough (90 min).** Send the report **one hour before** the call, not
days — you want to walk them through it live the first time so the framing is yours.
Order: attribution gap, spend to stop with the confidence-bound reasoning, spend you
cannot measure, then *ads that look worse than they are* (do not skip this; it proves
you are measuring rather than cost-cutting), then what you'd do next — named plainly and
once. Then stop talking.

**The transition.** Ask exactly one question at the end:

> The audit is a snapshot. Everything in it drifts back within about a quarter as
> creative fatigues and new ads launch. Do you want to run this yourself from the config
> I'm leaving you, or should I keep it running?

Both answers are fine. Roughly 40% take the second, and the ones who take the first
often come back a quarter later.

### Managed Acquisition — the weekly loop

**Onboarding (~4 hrs, once).** The pipeline already exists from the audit. Deploy per the
main README's Railway section — `adagent worker` and `adagent scheduler` plus Railway
Postgres, then `railway run adagent db migrate`. Set `ADAGENT_META__DRY_RUN=true`,
`max_actions_per_day: 10`, `human_approval_spend_threshold: 200.0`.

**Weeks 1–2 — dry-run.** The agent decides and records; nothing reaches Meta. Read
`adagent actions --days 7` against what you would have done, and send the client a short
weekly note: *"here's what it would have done, here's what I agree with, here's what I
don't and why."* Highest-trust artifact in the whole engagement, and it costs an hour.

**Going live.** Flip `ADAGENT_META__DRY_RUN=false`, keep the approval threshold low, work
`adagent actions --pending` and `adagent approve <id>`. Raise the thresholds gradually
over *months* as the ledger accumulates decisions you agreed with. There is no reward for
rushing this.

**Every week (~4 hrs/client):** review the week's decisions (45 min), clear the approval
queue (30 min), check economics against expectation (30 min), confirm entropy isn't
collapsing (15 min), write the client summary (45 min), buffer (75 min).

**Monthly:** re-run `adagent audit` and send it. It shows trend rather than snapshot and
is the single most effective retention artifact you have — the client watches the waste
line fall month over month. Re-tune thresholds against current margin at the same time.

**If something goes wrong:** `kill_switch: true` in `thresholds.yaml` freezes all writes
immediately. Then tell the client before they notice. Every decision is in
`agent_actions` with the exact metrics that justified it, so a post-mortem is always
possible and always specific. That is why the ledger exists.

---

## 8. The weekly cadence

| Day | Block | Hours |
|---|---|---|
| Mon | **Sales.** 40 outbound touches. Update the pipeline. | 3 |
| Tue | **Delivery.** Retainer reviews — read `adagent actions` per client, approve or override, send a 5-line summary. | 4 |
| Wed | **Sales.** 40 touches + every call booked this week. | 4 |
| Thu | **Delivery.** Audit production, one start to finish. | 6 |
| Fri | **Delivery + admin.** Remaining retainer work, invoicing, one public post. | 4 |
| — | Buffer | 3 |

**The rule that matters:** never skip Monday or Wednesday. Delivery work always feels
more urgent than sales work and is always less important, because delivery is already
paid for and sales is not.

---

## 9. What can go wrong

- **You cannot get warehouse access.** Some clients will not grant Stripe or CRM access
  to a stranger. The audit degrades gracefully — Meta + GA4 alone still produces the
  attribution-gap number. Say up front which sections will be blank.
- **Delivery crowds out sales.** The single most common way this stalls at $2,000/week.
  The Monday/Wednesday rule exists for exactly this.
- **You sell a number the account then misses.** Every projection in the audit is
  deliberately conservative — one capped budget step, net of added spend, at observed
  ROAS rather than the confidence bound. Do not inflate them in conversation.
- **Thresholds wrong for their margin structure.** A brand with a $40 AOV and one with a
  $4,000 contract value need entirely different numbers. Tune them on the first call and
  say openly that the audit's calls change when you do.
- **Reply rate comes in at 4% instead of 10%.** Then this takes twice as long. It is the
  main risk in the whole plan, and the fix is always targeting quality, never volume.
- **Meta App Review.** Only needed for *live writes at scale*. Audits and dry-run
  retainers do not require it — but file in week one, because it is calendar time you
  cannot compress.

---

## 10. The assumptions, so you can replace them

Everything in section 2's timeline rests on these. They are estimates. Replace them with
your own numbers after four weeks — that is the entire purpose of `pipeline.csv`.

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
| 1–2 | Build the list, ship the sample report, start outreach | — | $0 |
| 3–4 | First 1–2 audits sold and delivered | 2 audits | ~$1,250/wk |
| 5–8 | ~4 more audits; first 1–2 retainers convert | 6 audits, 2 retainers | ~$3,300/wk |
| 9–12 | Audits continue; retainers reach 4 | 10 audits, 4 retainers | **~$5,100/wk** |

**Pipeline stages**, in order: `researched` → `touched` → `replied` → `called` →
`audit_sold` → `audit_delivered` → `retainer`, or `lost` at any point. One row per
company, not per message. Delete the three example rows in `pipeline.csv` before you
start.

---

## Reference

| File | What it is |
|---|---|
| `sample-audit.md` | A complete report against a synthetic $48k/month account — your sales asset |
| `pipeline.csv` | The tracker |
| `offer.md`, `outreach.md`, `delivery.md`, `README.md` | The same material as this file, split by topic |
