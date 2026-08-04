"""Warehouse queries: identity-spine rebuild, mart refresh, and the read path.

## How an ad gets credited for revenue

Meta hands the browser an ``fbclid`` on click, but an fbclid does **not** tell you
which ad it came from — resolving one costs a Marketing API read, and doing that per
click is precisely the polling pattern that gets an app throttled or banned.

So the agent stamps its own ``ad_id`` into ``utm_content`` at publish time. That makes
the ad -> session hop deterministic and free. From there:

    ad_id (utm_content) -> session -> contact (fbclid / ga_client_id / email hash)
                                   -> stripe_customer -> payment

Revenue is credited back to the **click date**, not the payment date, so that spend
and revenue in any given row describe the same cohort. Crediting revenue on the day
the money arrived would smear a Tuesday click across a Friday row and make ROAS
meaningless.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from agent.config import AttributionConfig
from agent.domain import AdEconomics
from agent.logging_setup import get_logger
from agent.warehouse.client import WarehouseClient

log = get_logger(__name__)


REBUILD_IDENTITY_SQL = """
INSERT INTO bridge_click_identity
    (fbclid, ad_id, ga_client_id, contact_id, stripe_customer,
     email_sha256, match_method, match_confidence, first_seen_at)
SELECT
    fbclid, ad_id, ga_client_id, contact_id, stripe_customer,
    email_sha256, match_method, match_confidence, first_seen_at
FROM v_click_identity_build
"""


# Refresh mart_ad_economics for a date range.
#
# Deliberately explicit rather than a materialized view: this runs on a schedule the
# orchestrator controls, it is retryable, and it can be pointed at a fixture dataset
# in tests.
REFRESH_MART_SQL = """
INSERT INTO mart_ad_economics
    (ad_id, adset_id, campaign_id, day, impressions, clicks, spend,
     platform_conversions, attributed_conversions, attributed_revenue,
     lifetime_spend, lifetime_conversions, lifetime_impressions,
     daily_budget, attribution_confidence, window_matured)
WITH
    -- Meta's side: what we spent and what it bought in raw traffic.
    daily_spend AS (
        SELECT
            ad_id,
            any(adset_id)                AS adset_id,
            any(campaign_id)             AS campaign_id,
            toDate(hour)                 AS day,
            sum(impressions)             AS impressions,
            sum(clicks)                  AS clicks,
            sum(spend)                   AS spend,
            sum(platform_conversions)    AS platform_conversions
        FROM fact_ad_performance_hourly
        WHERE toDate(hour) BETWEEN {start:Date} AND {end:Date}
        GROUP BY ad_id, day
    ),

    -- Stripe's side, walked back through the identity spine to the originating ad
    -- and the day of the click. Revenue is net of refunds and normalised to the
    -- reporting currency at the payment-date rate.
    attributed AS (
        SELECT
            b.ad_id                                              AS ad_id,
            toDate(b.first_seen_at)                              AS day,
            count(DISTINCT p.payment_id)                         AS attributed_conversions,
            sum((p.amount_gross - {refund_factor:Float64} * p.amount_refunded)
                * p.fx_to_reporting)                             AS attributed_revenue,
            avg(b.match_confidence)                              AS attribution_confidence
        FROM bridge_click_identity AS b
        INNER JOIN fact_payment AS p
            ON p.stripe_customer = b.stripe_customer
        WHERE b.ad_id != ''
          AND b.stripe_customer != ''
          -- Payment must fall inside the lookback window that starts at the click.
          AND p.occurred_at >= b.first_seen_at
          AND p.occurred_at < b.first_seen_at + INTERVAL {lookback:UInt32} DAY
          AND toDate(b.first_seen_at) BETWEEN {start:Date} AND {end:Date}
        GROUP BY ad_id, day
    ),

    joined AS (
        SELECT
            s.ad_id                                   AS ad_id,
            s.adset_id                                AS adset_id,
            s.campaign_id                             AS campaign_id,
            s.day                                     AS day,
            s.impressions                             AS impressions,
            s.clicks                                  AS clicks,
            s.spend                                   AS spend,
            s.platform_conversions                    AS platform_conversions,
            ifNull(a.attributed_conversions, 0)       AS attributed_conversions,
            ifNull(a.attributed_revenue, toDecimal64(0, 6))  AS attributed_revenue,
            ifNull(a.attribution_confidence, 1.0)     AS attribution_confidence
        FROM daily_spend AS s
        LEFT JOIN attributed AS a ON a.ad_id = s.ad_id AND a.day = s.day
    )

SELECT
    j.ad_id,
    j.adset_id,
    j.campaign_id,
    j.day,
    j.impressions,
    j.clicks,
    j.spend,
    j.platform_conversions,
    j.attributed_conversions,
    j.attributed_revenue,

    -- Running totals across the ad's whole life. The sample-size floor and the
    -- learning-phase check both need history, not a single day.
    sum(j.spend) OVER w                  AS lifetime_spend,
    sum(j.attributed_conversions) OVER w AS lifetime_conversions,
    sum(j.impressions) OVER w            AS lifetime_impressions,

    ifNull(d.daily_budget, toDecimal64(0, 6)) AS daily_budget,
    j.attribution_confidence,

    -- The maturity gate. A day is only judgeable once the attribution lag has
    -- fully elapsed; until then its revenue is still arriving.
    if(j.day <= toDate(now('UTC') - INTERVAL {lag_hours:UInt32} HOUR), 1, 0) AS window_matured
FROM joined AS j
LEFT JOIN dim_ad AS d ON d.ad_id = j.ad_id
WINDOW w AS (PARTITION BY j.ad_id ORDER BY j.day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
"""


# The decision engine's read. One row per ad: its most recent matured day, carrying
# lifetime totals. `FINAL` collapses ReplacingMergeTree duplicates so a re-run of the
# mart refresh cannot double-count.
LATEST_ECONOMICS_SQL = """
SELECT
    ad_id, adset_id, campaign_id, day,
    impressions, clicks, spend,
    platform_conversions, attributed_conversions, attributed_revenue,
    lifetime_spend, lifetime_conversions, lifetime_impressions,
    daily_budget, attribution_confidence, window_matured
FROM mart_ad_economics FINAL
WHERE day >= {since:Date}
ORDER BY ad_id, day
"""


class WarehouseQueries:
    def __init__(self, client: WarehouseClient) -> None:
        self._client = client

    def rebuild_identity_bridge(self) -> None:
        log.info("warehouse.identity_bridge.rebuild_start")
        self._client.command(REBUILD_IDENTITY_SQL)
        log.info("warehouse.identity_bridge.rebuild_done")

    def refresh_mart(self, start: date, end: date, attribution: AttributionConfig) -> None:
        log.info("warehouse.mart.refresh_start", start=str(start), end=str(end))
        self._client.command(
            REFRESH_MART_SQL,
            parameters={
                "start": start,
                "end": end,
                "lookback": attribution.lookback_days,
                "lag_hours": attribution.lag_hours,
                "refund_factor": 1.0 if attribution.net_of_refunds else 0.0,
            },
        )
        log.info("warehouse.mart.refresh_done")

    def load_ad_economics(self, since: date) -> list[AdEconomics]:
        """Aggregate the mart into one decision-ready record per ad.

        Day rows are folded into a single per-ad view: windowed spend/revenue come
        from matured days only, while lifetime totals are taken from the latest row.
        """
        rows = self._client.query(LATEST_ECONOMICS_SQL, {"since": since})
        by_ad: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_ad.setdefault(str(row["ad_id"]), []).append(row)

        results: list[AdEconomics] = []
        for ad_id, ad_rows in by_ad.items():
            ad_rows.sort(key=lambda r: r["day"])
            latest = ad_rows[-1]
            matured = [r for r in ad_rows if int(r["window_matured"]) == 1]
            # No matured day yet: surface the ad but mark it unjudgeable. The
            # guardrails will refuse to act on it rather than the engine guessing.
            source = matured if matured else ad_rows

            results.append(
                AdEconomics(
                    ad_id=ad_id,
                    adset_id=str(latest["adset_id"]),
                    campaign_id=str(latest["campaign_id"]),
                    day=latest["day"],
                    impressions=sum(int(r["impressions"]) for r in source),
                    clicks=sum(int(r["clicks"]) for r in source),
                    spend=sum((_dec(r["spend"]) for r in source), Decimal("0")),
                    platform_conversions=sum(int(r["platform_conversions"]) for r in source),
                    attributed_conversions=sum(int(r["attributed_conversions"]) for r in source),
                    attributed_revenue=sum(
                        (_dec(r["attributed_revenue"]) for r in source), Decimal("0")
                    ),
                    lifetime_spend=_dec(latest["lifetime_spend"]),
                    lifetime_conversions=int(latest["lifetime_conversions"]),
                    lifetime_impressions=int(latest["lifetime_impressions"]),
                    daily_budget=_dec(latest["daily_budget"]),
                    attribution_confidence=float(latest["attribution_confidence"]),
                    window_matured=bool(matured),
                )
            )
        return results

    def concept_spend_split(self) -> dict[str, Decimal]:
        """Spend split between externally-seeded concepts and our own descendants."""
        rows = self._client.query(
            "SELECT is_external_dna, sum(spend) AS spend FROM v_concept_spend "
            "GROUP BY is_external_dna"
        )
        split = {"external": Decimal("0"), "internal": Decimal("0")}
        for row in rows:
            key = "external" if int(row["is_external_dna"]) == 1 else "internal"
            split[key] = _dec(row["spend"])
        return split


def _dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))
