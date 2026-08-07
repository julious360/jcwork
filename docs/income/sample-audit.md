# Paid acquisition audit — Northwind Supply Co.

> **Sample report — synthetic data.** The account below does not exist. It is
> shaped like a mid-size DTC brand spending roughly $48k/month so the format,
> the arithmetic, and the tone are representative of a real deliverable. Every
> number was produced by `adagent audit` from the same decision rules the agent
> runs in production.

Window: last **30 days** · Generated: **07 August 2026** · Currency: **USD**

---

## What this is worth

**$18,660 per month** is currently unrecovered — the sum of spend that is provably not returning and revenue that funding existing winners would return.

- **$9,150/mo** on ads with no defensible return (3 ads)
- **$9,510/mo** in net revenue left on the table by underfunded winners (2 ads)
- **$7,700/mo** flowing through ads whose outcome the current tracking cannot resolve at all (2 ads)

Meta reports **876** conversions in this window. **410** can be traced to a payment. That is a **53% gap** between the dashboard the account is optimised against and the revenue it is judged on.

## The window at a glance

| Metric | Value |
|---|---|
| Ads reviewed | 12 |
| Spend | $48,140 |
| Attributed revenue | $98,980 |
| Blended ROAS | 2.06x |
| Blended CPA | $117 |
| Conversions — Meta reported | 876 |
| Conversions — traced to payment | 410 |
| Attribution gap | 53% |

## 1. Spend to stop

Each of these has spent past the sample-size floor, sits outside the attribution lag, and still fails its limit on the *optimistic* end of its confidence interval. These are not close calls.

| Ad | Spend | Revenue | ROAS | Monthly spend recovered | Why |
|---|---:|---:|---:|---:|---|
| `ad_meme_test_03` | $3,900 | $0 | 0.00x | $3,900 | no attributed conversions after 3900 spend (>3.0x target CPA) |
| `ad_discount_led` | $2,850 | $1,140 | 0.40x | $2,850 | CPA upper bound 543.94 exceeds max 90.00 at 90% confidence |
| `ad_influencer_b` | $2,400 | $0 | 0.00x | $2,400 | no attributed conversions after 2400 spend (>3.0x target CPA) |

## 2. Spend to add

These clear the scale benchmark on the *pessimistic* end of their interval and are out of the learning phase. The figure below is one capped budget step, net of the added spend — not a compounding projection.

| Ad | Spend | Revenue | ROAS | Net monthly revenue added | Why |
|---|---:|---:|---:|---:|---|
| `ad_ugc_founder_01` | $8,400 | $41,160 | 4.90x | $6,552 | ROAS lower bound 4.23 exceeds scale benchmark 2.50; raising budget 280 -> 336.00 (+20% cap) |
| `ad_review_carousel` | $5,100 | $19,890 | 3.90x | $2,958 | ROAS lower bound 3.21 exceeds scale benchmark 2.50; raising budget 170 -> 204.00 (+20% cap) |

## 3. Spend you cannot currently measure

Identity resolution on these ads is too weak to confirm or rule out revenue. They are neither wins nor losses today — they are blind spots, and they are the first thing worth fixing, because every other number on this page gets better when they shrink.

| Ad | Spend | Revenue | ROAS | Monthly spend affected | Why |
|---|---:|---:|---:|---:|---|
| `ad_retarget_dpa` | $5,600 | $9,800 | 1.75x | $5,600 | identity match confidence 0.42 is below 0.80 — revenue for this ad cannot be confirmed or ruled out |
| `ad_email_lookalike` | $2,100 | $3,150 | 1.50x | $2,100 | identity match confidence 0.55 is below 0.80 — revenue for this ad cannot be confirmed or ruled out |

## 4. Ads that look worse than they are

2 ads fall inside the attribution lag: the spend is booked but the revenue has not finished landing. On a Meta dashboard they read as failures today. Pausing them now is the single most common way a well-run account loses a winner.

| Ad | Spend | Revenue so far |
|---|---:|---:|
| `ad_fall_launch_a` | $4,100 | $2,050 |
| `ad_fall_launch_b` | $3,050 | $1,220 |

## How these numbers were produced

Revenue is not taken from Meta. Every figure above comes from a join that walks each click through to a settled payment:

```
ad id (stamped into utm_content) → web session → CRM contact → payment processor → payment
```

Four properties of that method are worth stating, because they are what make the conclusions differ from the platform's own reporting:

1. **Revenue is credited to the click date, not the payment date.** Spend and revenue on the same row describe the same cohort. Crediting on payment date smears a Monday click across a Friday row and makes ROAS meaningless.
2. **Revenue is net of refunds.** Gross revenue flatters every ad that sells to the wrong customer.
3. **The trailing attribution lag is excluded from judgement**, not counted as failure. Ads inside it appear in their own section above rather than being scored.
4. **Every hop records how it matched and how confident that match is.** A deterministic pass-through is not the same quality of evidence as an email-hash join, and low-confidence ads are reported as unmeasurable rather than scored on numbers that cannot bear it.

Pause and scale calls are made on **confidence bounds, not point estimates** — an ad is only called wasteful when the optimistic end of its interval still fails, and only called underfunded when the pessimistic end still clears. Ads below the sample-size floor or inside the platform learning phase are not judged at all.

## What this audit does not tell you

- **Whether the thresholds are right for this account.** The limits applied here are the configured ones. Tuning them against this account's real margin structure is a separate exercise, and it changes some of the calls above.
- **Whether the creative is good.** This measures money, not ideas. An ad can clear every bound here and still be the reason the brand looks generic.
- **Incrementality.** Attributed revenue is revenue that followed a click. Proving the click *caused* the purchase needs a holdout test, which this window does not contain.
- **2 ads could not be measured at all** at the confidence floor used here. Until that is fixed, treat the totals above as a lower bound on what is knowable.
