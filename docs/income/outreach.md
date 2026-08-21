# Outreach

The entire approach depends on the list being narrow enough that every message can
reference something specific and true. 50 researched companies beats 500 scraped ones,
and the difference shows up as a 10% reply rate instead of 1%.

---

## Who to target

Three filters, all of which must hold:

1. **Spending $30k–$250k/month on Meta.** Below $30k the audit is hard to justify
   against their budget. Above $250k they have an in-house team and a procurement
   process, and the sales cycle stops being 5 days.
2. **Sells something with a traceable payment** — DTC ecommerce on Shopify/Stripe, or
   B2B SaaS with a CRM. If money changes hands offline, the identity spine has nothing
   to join on and you cannot deliver.
3. **Has a revenue lag.** Subscription, high-consideration, or long sales cycle. This
   is the sharpest filter: lag is precisely what makes platform-reported conversions
   diverge from banked revenue, so these accounts have the largest gap and feel the
   pain most.

### Where to find them

- **Meta Ad Library.** Filter by category, sort by ads running longest. An advertiser
  running the same creative for 90+ days is spending real money and is not iterating —
  the exact profile that has a measurement problem.
- **Shopify app store reviews** for attribution tools (Triple Whale, Northbeam,
  Hyros). Reviewers describing what still doesn't work are pre-qualified: they know
  they have the problem and have already paid to try to solve it.
- **Agencies, not just brands.** A 10-client agency is one relationship that can
  become several. Sell them the audit as something they white-label to their own
  clients — many will, and that is your highest-leverage channel.
- **Job boards.** A company hiring a "Growth Analyst — attribution" has budget and an
  admitted problem. Do not apply. Offer the audit to the hiring manager.

### Disqualify fast

Lead-gen with offline close, anything under $30k/month spend, anyone who says
"we're happy with our Meta reporting." The last one is not a prospect to educate; it
is a prospect to skip.

---

## The messages

Three rules for all of them: **name a specific observation about them**, **make one
ask**, and **never attach anything on the first touch**.

### Cold email — first touch

> Subject: 410 of 876
>
> Hi {name} — I pulled {company} in the Meta Ad Library and you've had the
> {specific creative} running since {month}, which usually means it's working.
>
> Quick question about how you're measuring that. On most accounts I look at, Meta
> reports roughly twice the conversions that can actually be traced through to a
> payment — view-through and modelled conversions the platform counts and your bank
> account doesn't. On a synthetic $48k/month account I ran last week the gap was 53%,
> and about $18k/month of spend was sitting on the wrong side of it.
>
> I'm not going to guess at yours. Worth 15 minutes to find out?
>
> — {you}

Why it works: it opens with proof you looked, states a specific and checkable claim,
and asks for time rather than a sale.

### Follow-up — 4 days later

> Following up on the above with the thing itself rather than a description of it —
> here's a full report against a synthetic account so you can see exactly what you'd
> get: {link}
>
> The part most people go to first is section 3, "spend you cannot currently measure."
> That's usually the number that decides whether this is worth your time.
>
> Still happy to run yours. Read-only access, nothing touches the account.

### LinkedIn DM — shorter

> {name} — noticed {company} is running {N} creatives on Meta right now. Do you
> reconcile those conversion numbers against Stripe, or work off the Meta dashboard?
>
> Asking because the gap is usually ~50% and almost nobody's measuring it. Wrote up a
> full example here if useful: {link}

### To an agency

> {name} — you're running paid social for {N} clients. How are you handling the fact
> that Meta's reported conversions and your clients' actual revenue don't reconcile?
>
> I've built the join that closes it — ad → session → CRM → Stripe, revenue credited
> to click date, net of refunds. I sell it as a $2.5k audit, and a few agencies
> white-label it as their own quarterly deliverable.
>
> Worth a conversation?

---

## The call

30 minutes. Structure:

1. **(5 min) What do you optimise against today?** Let them say "Meta's dashboard"
   or "Triple Whale." Do not correct anything yet.
2. **(5 min) Have you reconciled that to Stripe?** Almost always no, or "roughly."
   This is the moment the problem becomes theirs rather than yours.
3. **(10 min) Walk the sample report.** Screen share. Go to the attribution gap first,
   then spend-to-stop, then — importantly — section 4, "ads that look worse than they
   are." That section is what proves you are not just another dashboard salesman
   telling them to cut spend.
4. **(5 min) Scope and price.** $2,500, five days, read-only, and if it finds less
   than $2,500/month in recoverable spend they don't pay.
5. **(5 min) Access.** Name exactly what you need: Meta read-only, GA4 viewer,
   CRM read, Stripe read-only key. Send the list in writing the same day.

**Do not do a custom analysis before they pay.** The sample report is the free
version. It is enough.

---

## Objections

**"We already use Triple Whale / Northbeam / Hyros."**
> Good — then you already believe the platform numbers are wrong. Those tools model
> the gap. This one joins through to the actual payment and tells you the confidence
> of every match, so you can see which conclusions are load-bearing and which aren't.
> If they agree, that's worth knowing too.

**"Can't my agency do this?"**
> They can tell you what Meta reported. The question is whether they can tell you what
> Stripe settled, credited back to the click date and net of refunds. Ask them — it's
> a fair question and the answer is informative either way.

**"$2,500 is a lot for a report."**
> It's about a week of your ad spend. If it finds nothing worth $2,500/month you don't
> pay. And on the sample account it found $18,660/month — I'd rather show you a small
> number honestly than a big one I made up.

**"I don't want anyone touching my ad account."**
> Nothing touches it. The audit is read-only, and even the ongoing service runs two
> weeks in dry-run first — it records every decision it would have made without
> making any, and you read the log before granting write access. That's the default,
> not a concession.

**"Send me some information."**
> Sending the sample report now. One thing worth flagging before you read it: the
> number that usually matters isn't the waste, it's section 3 — the spend nobody can
> measure at all. Happy to talk once you've had a look.

**"We're too small."**
> Probably true under $30k/month — the recoverable spend won't cover the fee, and I'd
> rather say that now. Worth revisiting when you're past it.

Say the last one when it's true. Turning away a bad fit costs one deal and buys a
referral more often than not.

---

## Tracking

Log every touch in [`pipeline.csv`](pipeline.csv). After four weeks you will have real
numbers for reply rate, call rate, and close rate — replace the estimates in
[`README.md`](README.md) with them. The ramp projection is only useful once it is
built from your own funnel rather than a plausible guess.
