# adagent — autonomous Facebook Ads marketing agent

A self-optimising loop: it researches customer pain points, generates and validates
creative, publishes it, watches revenue land in a warehouse, then pauses losers and
scales winners — while deliberately injecting outside signal so it doesn't converge
on its own past ideas.

```
research ──► creative ──► publish ──►  Meta Ads
   ▲            ▲                          │
   │            │                          ▼
   │      entropy pool               Airbyte ETL
   │            ▲                          │
   │            │                          ▼
   └──── decision loop ◄──────────  ClickHouse warehouse
                                    (ad → click → CRM → Stripe)
```

## Three ideas the design turns on

**1. The warehouse is the agent's memory.** Meta can tell you an ad got a click. Only
a join through GA4 → HubSpot → Stripe can tell you that click became $4,200 of revenue
eleven days later. Every decision is made against `mart_ad_economics`, which carries
real attributed revenue net of refunds — not Meta's reported conversion values.

**2. The Meta API is write-only.** Meta meters the Marketing API per ad account in
points (reads 1, writes 3) against a quota that scales with spend, and the default
access tier is documented as unsuitable for production. Polling `/insights` is the
standard way to get throttled and restricted. So `agent/meta/write_client.py` has no
read methods — and `tests/test_meta_write_only.py` fails the build if one appears.

**3. Entropy is enforced, not hoped for.** An agent that only iterates on its own
winners converges: variance shrinks each generation until performance decays with no
visible cause. Every candidate concept is embedded and rejected if it's too similar to
what already shipped, and a configurable share of spend is reserved for concepts seeded
from *outside* the account.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # works as-is: everything mocks cleanly

docker compose up -d          # local ClickHouse + Postgres
adagent db migrate
adagent doctor                # shows which integrations are live vs mocked
```

Nothing above needs an API key. With no credentials the agent runs end to end against
mock providers; add keys and each path goes live independently.

```bash
adagent config                # active thresholds and guardrails
adagent research              # ranked top-3 pain points as JSON
adagent creative              # generate + brand-validate ad candidates
adagent harvest               # pull external DNA into the pool
adagent loop --dry-run        # decide against real data, write nothing
adagent actions               # the ledger: what it decided, and why
adagent audit                 # a client-ready report of the same conclusions
```

## Safety posture

`ADAGENT_META__DRY_RUN` defaults to **true**. In dry-run the agent does everything
except call Meta — decisions are still written to `agent_actions` with the exact
metrics that justified them. **Run it this way for at least a week and read the ledger
before granting write access.** The decisions are the product; executing them is the
easy part.

Beyond dry-run:

| Guard | What it prevents |
|---|---|
| Sample-size floor (3× target CPA) | Pausing a good ad on ten clicks of noise |
| Confidence bounds, not point estimates | Churning budget on statistical wobble |
| Attribution maturity gate (48h) | Killing every recent ad because Stripe lags Meta |
| Learning-phase protection | Scaling before delivery has stabilised |
| Budget increase cap (20%/24h) | Resetting learning with a big jump |
| Action caps (per run / per day) | A bad config emptying the account overnight |
| Human approval above a spend threshold | Large changes going through unseen |
| `kill_switch: true` | Everything, immediately |
| Idempotency keys claimed pre-send | A retry after a timeout creating a second ad |
| Persisted circuit breaker | A deploy stampeding an account that's throttling |

New campaigns, adsets, and ads are always created **PAUSED**.

## Configuration

Three YAML files under `agent/config/` — in version control, so a threshold change
that will pause real ads shows up in a diff:

- **`campaign.yaml`** — the vertical. Category, ICP, research seeds, entropy sources.
  Nothing product-specific is compiled into the code; swap this file, keep the agent.
- **`thresholds.yaml`** — CPA/ROAS rules, every guardrail, attribution model.
- **`brand_guide.yaml`** — palette and Meta ad spec (checked in code), plus tone and
  logo rules (judged by a vision model).

Secrets come from environment variables only. See `.env.example`.

## How attribution works

Meta hands the browser an `fbclid`, but an fbclid doesn't tell you which ad it came
from — resolving one costs a Marketing API read, and doing that per click is exactly
the polling pattern we refuse. So the agent stamps its own id into `utm_content` at
publish time, making the first hop deterministic and free:

```
ad_id (utm_content) → GA4 session → HubSpot contact → Stripe customer → payment
```

Every hop records `match_method` and `match_confidence`; a deterministic pass-through
is not the same quality of evidence as an email-hash join, and the decision engine
refuses to act when confidence is low. Revenue is credited back to the **click date**,
not the payment date, so spend and revenue in a row describe the same cohort.

## Brand validation is two-stage, by design

Stage 1 is code: real pixel palette compared against the brand hexes as CIE76 ΔE in
Lab space, plus dimensions, aspect ratio, and file size against Meta's spec. Stage 2 is
a vision model, for tone, composition, logo placement, and forbidden claims.

A failing stage 1 short-circuits — no tokens are spent on an image a histogram already
rejected. Asking a model whether an image is 1080px wide is slower, costlier, and less
reliable than measuring it.

## Layout

```
agent/
  config/       settings + the three YAML configs
  warehouse/    ClickHouse client, attribution SQL, mart refresh   ← the read path
  ops/          Postgres: job queue, action ledger, idempotency, breaker
  research/     pain-point providers + composite ranking
  creative/     copy, images, two-stage validation, ffmpeg stitching
  meta/         write-only client + rate governor                  ← the write path
  decision/     rules, statistics, guardrails, engine
  entropy/      DNA pool, novelty gate, external harvesters
  orchestrator/ jobs, worker, scheduler
migrations/     clickhouse/ + postgres/
airbyte/        pipeline as code
```

**Why two databases.** ClickHouse is the analytical memory. Postgres holds state that
must be transactional: "I paused ad X" has to be recorded exactly once and an
idempotency key has to be atomically claimable. ClickHouse promises neither.

## Deployment (Railway)

Two services from this repo, plus Railway Postgres:

| Service | Command |
|---|---|
| worker | `adagent worker` |
| scheduler | `adagent scheduler` |

Point `ADAGENT_CLICKHOUSE__*` at ClickHouse Cloud with `SECURE=true`, set
`ADAGENT_POSTGRES__DSN` from Railway's `DATABASE_URL`, then run `railway run adagent db
migrate` once. `airbyte/connections.yaml` defines the ETL.

## Integration status

| Path | Status |
|---|---|
| ClickHouse warehouse + attribution | live |
| Postgres ops, queue, ledger, breaker | live |
| Decision engine + guardrails | live |
| Meta write client + rate governor | live, dry-run until credentialed |
| Copy generation (Claude) | live with a key |
| Image generation (Gemini) | live with a key |
| Brand validation (deterministic + vision) | live |
| Research (Perplexity / Reddit) | interface + mock; live with keys |
| Video (HeyGen / Seedance) | interface + mock — `generate_segment` needs implementing |
| Ad Library / YouTube / podcast harvest | live, opt-in via `campaign.yaml` |

Every mocked path implements the same protocol as its live counterpart, so swapping one
in is a constructor change.

## Known limits

- **Video providers are declared, not implemented.** `HeyGenProvider` and
  `SeedanceProvider` raise `NotImplementedError` with instructions. The stitching,
  scripting, and DNA plumbing around them is real.
- **Ad Library harvest covers pages you name.** Meta's official API only supports broad
  keyword search for political ads. Scraping the public UI would widen coverage but
  breaks Meta's terms, so it isn't included.
- **Podcast harvest reads show notes, not audio.** Whisper transcription needs its own
  budget and queue.
- **Airbyte's raw stream names need mapping** to the tables in
  `migrations/clickhouse/001_dimensions.sql` via `stg_` views for your connector
  versions.
- **Embeddings fall back to a local hashing embedder** when no embedding API is
  reachable. It reliably catches near-duplicates; it is weaker at deep semantic
  similarity.

## Testing

Five tiers, cheapest first. Each one buys a different kind of confidence, and you can
stop at any of them.

### 1. Offline — no setup, no credentials, no databases

```bash
pytest                              # 132 tests, ~2s
ruff check agent tests && mypy agent
```

Covers the decision rules and every guardrail, the rate governor (including simulated
throttle headers and Meta's `estimated_time_to_regain_access`), brand validation
against real generated PNGs, novelty gating, dry-run and idempotency behaviour, and
the write-only constraint. Every migration and runtime query is parsed with `sqlglot`
in the correct dialect, so SQL errors surface here rather than at deploy.

```bash
pytest tests/test_meta_write_only.py -v   # the constraint that protects the account
pytest tests/test_decision_rules.py -v    # the guardrails that protect the budget
```

### 2. Local databases — the warehouse path end to end

This is the tier that proves attribution actually works.

```bash
docker compose up -d
adagent db migrate
adagent seed        # synthetic ads: a loser, a winner, an under-sampled ad, an immature one
adagent verify      # runs the real loop and checks it reached the right conclusions
```

`verify` exercises the full chain — migrations, identity spine, attribution SQL, mart
refresh, decision engine — and prints a pass/fail line per scenario. Revenue is seeded
through the *whole* path (session → contact → Stripe customer), not written into the
mart, so a broken join surfaces as a wrong decision rather than passing quietly.

Expected output:

```
PASS  ad_loser       expected pause_ad       got pause_ad
PASS  ad_winner      expected scale_budget   got scale_budget
PASS  ad_young       expected no_op          got no_op
PASS  ad_immature    expected no_op          got no_op
```

The last two are the ones worth watching. A naive threshold check pauses both.

Then inspect what it saw and why:

```bash
adagent economics    # the warehouse view the engine reads
adagent actions      # the ledger, with the reasoning behind each decision
adagent audit        # the same conclusions, written for someone who won't run the CLI
```

`adagent audit` is read-only: it evaluates the account through the same `evaluate_ad`
path the loop uses, but touches neither Meta nor the ledger. A test asserts that its
waste and scale findings match the engine's own verdicts, because a report that
recommends something the agent would not do is worse than no report. See
[`docs/income/sample-audit.md`](docs/income/sample-audit.md) for a full example.

### 3. With LLM keys — real research and creative

Set `ADAGENT_LLM__ANTHROPIC_API_KEY` and `ADAGENT_LLM__GEMINI_API_KEY`:

```bash
adagent doctor       # confirms the paths flipped from mock to live
adagent research     # real ranked pain points from real sources
adagent creative     # real images, really brand-validated
```

Costs cents. Check the generated files in `artifacts/` and read the ranked JSON —
this is the tier where you judge output *quality*, which no assertion can do for you.

### 4. With Meta credentials, still dry-run — the real proving ground

Point Airbyte at your accounts, keep `ADAGENT_META__DRY_RUN=true`, and let the
scheduler run for a week against live data. The agent decides and records but never
calls Meta.

```bash
adagent actions --days 7
```

Read every decision against what you would have done. **This is the tier that
matters** — it is the only way to find out whether your thresholds are right for your
account before they cost anything. Nothing else substitutes for it.

### 5. Live — smallest budget you can tolerate

Set `dry_run=false` on one low-spend campaign. Keep `max_actions_per_day` low and
`human_approval_spend_threshold` low so you see decisions before they land. Flip
`kill_switch: true` in `thresholds.yaml` to freeze everything instantly.

### What the tests deliberately do not cover

- **Live vendor calls.** Meta, Perplexity, Reddit, and HeyGen are mocked; contract
  drift on their side won't be caught here.
- **Whether the thresholds are right for your account.** Tier 4 is the only answer.
- **Creative quality.** The validator checks palette, spec, tone, and claims. Whether
  an ad *works* is a question only spend answers.
