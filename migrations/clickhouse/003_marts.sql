-- mart_ad_economics: the single table the decision engine reads.
--
-- Grain: ad_id x day. Populated by an explicit INSERT ... SELECT from the
-- orchestrator (see agent/warehouse/queries.py) rather than a materialized view,
-- so refreshes are observable, retryable, and testable.
--
-- The `window_matured` column is the one that prevents the most expensive class of
-- mistake this agent can make. Spend is recorded instantly; Stripe revenue lands
-- hours-to-days later. Judged naively, every recent ad looks like a catastrophic
-- loser and gets paused. Rows whose day is still inside the attribution lag are
-- written with window_matured = 0 and are ignored by the pause rules.

CREATE TABLE IF NOT EXISTS mart_ad_economics
(
    ad_id                    String,
    adset_id                 String,
    campaign_id              String,
    day                      Date,

    impressions              UInt64  DEFAULT 0,
    clicks                   UInt64  DEFAULT 0,
    spend                    Decimal(18, 6) DEFAULT 0,

    platform_conversions     UInt64  DEFAULT 0,
    attributed_conversions   UInt64  DEFAULT 0,
    attributed_revenue       Decimal(18, 6) DEFAULT 0,

    -- Rolling lifetime totals: the sample-size floor and learning-phase check need
    -- the ad's whole history, not one day of it.
    lifetime_spend           Decimal(18, 6) DEFAULT 0,
    lifetime_conversions     UInt64  DEFAULT 0,
    lifetime_impressions     UInt64  DEFAULT 0,

    daily_budget             Decimal(18, 6) DEFAULT 0,
    attribution_confidence   Float32 DEFAULT 1.0,
    window_matured           UInt8   DEFAULT 0,

    _built_at                DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_built_at)
PARTITION BY toYYYYMM(day)
ORDER BY (ad_id, day);


-- Concept-level rollup for the anti-entropy exploration budget: how much spend is
-- going to externally-seeded concepts versus descendants of our own past winners.
CREATE VIEW IF NOT EXISTS v_concept_spend AS
SELECT
    d.concept_family_id                             AS concept_family_id,
    max(d.is_external_dna)                          AS is_external_dna,
    sum(m.spend)                                    AS spend,
    sum(m.attributed_revenue)                       AS revenue,
    sum(m.attributed_conversions)                   AS conversions,
    count(DISTINCT m.ad_id)                         AS ad_count
FROM mart_ad_economics AS m
INNER JOIN dim_ad AS d ON d.ad_id = m.ad_id
WHERE d.concept_family_id != ''
GROUP BY concept_family_id;
