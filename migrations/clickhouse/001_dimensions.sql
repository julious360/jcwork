-- Dimensions and the raw fact tables fed by Airbyte.
--
-- Layering: Airbyte lands raw streams -> stg_ views type and dedupe them ->
-- these tables and the marts in 003 are what the agent reads. The agent NEVER
-- calls the Meta API to read any of this.

CREATE TABLE IF NOT EXISTS dim_ad
(
    ad_id             String,
    adset_id          String,
    campaign_id       String,
    ad_name           String,
    adset_name        String,
    campaign_name     String,
    creative_id       String,

    -- Our own lineage, joined back from Postgres `creative_assets`. This is what
    -- makes the anti-entropy layer able to reason about what has already been tried.
    dna_id            String DEFAULT '',
    concept_family_id String DEFAULT '',
    is_external_dna   UInt8  DEFAULT 0,

    status            LowCardinality(String),
    effective_status  LowCardinality(String),
    daily_budget      Decimal(18, 6) DEFAULT 0,
    created_time      DateTime64(3, 'UTC'),
    _synced_at        DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_synced_at)
ORDER BY ad_id;


CREATE TABLE IF NOT EXISTS fact_ad_performance_hourly
(
    ad_id                  String,
    adset_id               String,
    campaign_id            String,
    hour                   DateTime('UTC'),

    impressions            UInt64  DEFAULT 0,
    clicks                 UInt64  DEFAULT 0,
    link_clicks            UInt64  DEFAULT 0,
    spend                  Decimal(18, 6) DEFAULT 0,
    currency               LowCardinality(String) DEFAULT 'USD',

    -- Meta's own numbers. Kept for reconciliation and learning-phase signals only;
    -- they are NOT the basis for ROAS. Note Meta removed 7d/28d view-through
    -- windows from ads_insights in Jan 2026, so these are click-based.
    platform_conversions   UInt64  DEFAULT 0,
    platform_conv_value    Decimal(18, 6) DEFAULT 0,

    _synced_at             DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_synced_at)
PARTITION BY toYYYYMM(hour)
ORDER BY (ad_id, hour);


-- GA4. Carries the fbclid captured on the landing page, which is the first hop
-- of the identity spine.
CREATE TABLE IF NOT EXISTS fact_web_session
(
    session_id     String,
    ga_client_id   String,
    fbclid         String DEFAULT '',
    utm_source     String DEFAULT '',
    utm_campaign   String DEFAULT '',
    utm_content    String DEFAULT '',   -- we stamp ad_id here at publish time
    landing_page   String DEFAULT '',
    email_sha256   String DEFAULT '',   -- set post-identification, never raw email
    started_at     DateTime64(3, 'UTC'),
    _synced_at     DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_synced_at)
PARTITION BY toYYYYMM(started_at)
ORDER BY (session_id, started_at);


CREATE TABLE IF NOT EXISTS fact_crm_contact
(
    contact_id      String,
    email_sha256    String DEFAULT '',
    fbclid          String DEFAULT '',
    ga_client_id    String DEFAULT '',
    lifecycle_stage LowCardinality(String) DEFAULT '',
    created_at      DateTime64(3, 'UTC'),
    _synced_at      DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_synced_at)
ORDER BY contact_id;


CREATE TABLE IF NOT EXISTS fact_crm_deal
(
    deal_id      String,
    contact_id   String,
    stage        LowCardinality(String) DEFAULT '',
    amount       Decimal(18, 6) DEFAULT 0,
    is_won       UInt8 DEFAULT 0,
    closed_at    Nullable(DateTime64(3, 'UTC')),
    created_at   DateTime64(3, 'UTC'),
    _synced_at   DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_synced_at)
ORDER BY deal_id;


-- Stripe. The only source of truth for revenue.
CREATE TABLE IF NOT EXISTS fact_payment
(
    payment_id        String,
    stripe_customer   String,
    email_sha256      String DEFAULT '',
    amount_gross      Decimal(18, 6) DEFAULT 0,
    amount_refunded   Decimal(18, 6) DEFAULT 0,
    currency          LowCardinality(String) DEFAULT 'USD',
    fx_to_reporting   Decimal(18, 8) DEFAULT 1,   -- rate at payment date
    is_first_payment  UInt8 DEFAULT 0,
    occurred_at       DateTime64(3, 'UTC'),
    _synced_at        DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_synced_at)
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (payment_id, occurred_at);
