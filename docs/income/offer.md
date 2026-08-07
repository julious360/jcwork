# The offer

Two SKUs. One is a wedge, one is the business. Resist adding a third — the reason this
sells is that the buyer understands it in one sentence.

---

## SKU 1 — Attribution Audit

**$2,500. Fixed price, fixed scope, delivered in 5 business days.**

> I'll show you how much of your Meta spend last month produced revenue you can trace
> to a bank deposit, and how much didn't. Fixed price, five days, and you keep the
> report whether or not we work together again.

### What they get

- A written report (see [`sample-audit.md`](sample-audit.md)) covering:
  - Blended ROAS and CPA computed from **settled payments**, not platform-reported
    conversions
  - The **attribution gap** — platform-reported conversions vs. conversions traceable
    to a payment
  - **Spend to stop** — ads past the sample-size floor that fail their limit even on
    the optimistic end of their confidence interval, with a monthly dollar figure
  - **Spend to add** — ads clearing the scale benchmark on the pessimistic end, with
    net monthly upside after the added spend
  - **Spend you cannot measure** — ads where identity resolution is too weak to judge
  - **Ads that look worse than they are** — spend inside the attribution lag that a
    dashboard reads as failure today
- A 90-minute walkthrough call, recorded
- The threshold set tuned to their margin structure, as a config file they keep

### What it costs you

6–9 hours, most of it waiting on data syncs. See [`delivery.md`](delivery.md).

### Why this price

$2,500 is deliberately below the threshold where procurement gets involved and above
the threshold where the buyer treats it as disposable. It is roughly one week of a
mid-size account's ad spend — which makes it trivially justifiable if the report finds
anything at all, and the sample account's report found $18,660/month.

### Explicitly not included

- Any change to their ad account. This is read-only. Say so early and often; it
  removes the largest objection before it is raised.
- Creative production
- Landing page or funnel work
- Ongoing monitoring — that is SKU 2

---

## SKU 2 — Managed Acquisition

**$5,500/month. 3-month minimum, then monthly. 30 days' notice.**

> The audit tells you what's wrong once. This keeps it from drifting back — the loop
> runs every 6 hours against real revenue, and you get a human reading every decision
> before it lands.

### What they get

- The decision loop running continuously against their account, deciding on real
  attributed revenue rather than platform-reported conversions
- **Two weeks of dry-run at the start of every engagement**, no exceptions. The agent
  decides and records but writes nothing. They read the ledger and see exactly what
  would have happened before anything does.
- Then live, with `human_approval_spend_threshold` set low and raised only as the
  ledger earns it
- Weekly written summary: what changed, what it cost, what it returned
- Monthly threshold review against actual margin
- Warehouse and attribution pipeline maintained

### What it costs you

~4 hours/week per client, most of it reviewing the ledger and writing the summary.

### Why this price

Below a full-time hire, below most agency retainers, and defensible against a single
number: if it recovers $8k/month of wasted spend on a $50k/month account, it pays for
itself 1.5x before any upside from scaling winners.

### Explicitly not included

- Creative production. Offer it separately if you want it; do not bundle it, because
  it is the part that does not scale and it will eat the margin on everything else.
- Guaranteed ROAS. Never. See below.

---

## Terms worth holding

**Payment.** Audit: 100% up front. Retainer: monthly in advance, first month on
signature. You are a one-person operation; you do not extend credit.

**Never guarantee ROAS.** You control spend allocation, not the market, the offer, or
the product. What you *can* guarantee, and should: "if the audit finds less than
$2,500/month in recoverable spend, you don't pay for it." That is a real guarantee you
control, it is honest, and it closes deals. The audit's conservatism is what makes it
safe to offer.

**Read-only until proven.** Both SKUs start without write access to anything. This is
the strongest trust-building asset you have — use it in the pitch, not just in the
contract.

**Scope creep.** The retainer covers spend allocation and attribution. The moment a
client asks for creative, landing pages, or email, it is a separate quote. Write this
into the agreement so the conversation is already had.

**Raise prices at 5 clients.** Capacity runs out around 5 retainers. When you get
there, raise the retainer to $7,500 for new clients rather than hiring. It is the
cleanest available margin, and hiring changes the business you are running.
