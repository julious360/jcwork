# finance.md — Finance Department

Parent: `claude.md`. Scope: what was spent, what came back, net of refunds.

## The one table that matters

`mart_ad_economics` (ClickHouse) — spend, attributed revenue, CPA, ROAS per ad,
joined ad → click → CRM → Stripe. Defined in `migrations/clickhouse/003_marts.sql`.
Identity stitching: `migrations/clickhouse/002_identity_bridge.sql`.

## Files

| File | Purpose |
|---|---|
| `agent/warehouse/queries.py` | every read the agent makes; add queries here, not inline |
| `agent/warehouse/client.py` | ClickHouse connection + migrations |
| `agent/decision/statistics.py` | confidence bounds on CPA/ROAS |
| `airbyte/connections.yaml` | GA4 / HubSpot / Stripe → warehouse ETL |

## Commands

```bash
adagent economics --days 14    # spend, attributed revenue, CPA, ROAS
adagent actions --limit 50     # spend-affecting decisions + approval queue
adagent verify                 # attribution sanity checks
```

## Rules of the department

- Revenue is **net of refunds** (`attribution.net_of_refunds: true`) and reported in
  `attribution.reporting_currency`. Never quote gross Stripe volume as revenue.
- The trailing `attribution.lag_hours` (48h) is excluded from every economics answer.
  A "sudden ROAS collapse" in the last two days is almost always lag, not loss.
- `human_approval_spend_threshold` (500.0) gates large changes — items in
  `awaiting_approval` are unbooked spend decisions, surface them in any finance summary.
- Attribution model: `last_non_direct_click`, 7-day lookback. State it whenever you
  hand over a number.
