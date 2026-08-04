-- The identity spine: ad click -> session -> CRM contact -> Stripe customer.
--
-- This is the piece that makes real ROAS possible. Meta can tell you an ad got a
-- click; only this join can tell you that click became $4,200 of Stripe revenue
-- eleven days later.
--
-- Every hop records HOW it was matched and how much to trust it. A deterministic
-- fbclid pass-through is not the same quality of evidence as an email-hash join,
-- and the decision engine is entitled to know the difference.

CREATE TABLE IF NOT EXISTS bridge_click_identity
(
    fbclid            String,
    ad_id             String DEFAULT '',
    ga_client_id      String DEFAULT '',
    contact_id        String DEFAULT '',
    stripe_customer   String DEFAULT '',
    email_sha256      String DEFAULT '',

    -- 'fbclid_passthrough' (deterministic) | 'email_hash' (probabilistic-ish)
    -- | 'utm_content' (we stamped ad_id ourselves at publish time)
    match_method      LowCardinality(String),
    match_confidence  Float32 DEFAULT 1.0,

    first_seen_at     DateTime64(3, 'UTC'),
    _built_at         DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_built_at)
ORDER BY (fbclid, contact_id, stripe_customer);


-- Rebuild the spine. Run before every mart refresh.
--
-- Resolution order matters: the strongest evidence wins. We take fbclid straight
-- from the session where present, fall back to the ad_id we stamped into
-- utm_content ourselves, and only then reach for an email-hash join.
CREATE VIEW IF NOT EXISTS v_click_identity_build AS
WITH sessions AS (
    SELECT
        s.fbclid                          AS fbclid,
        s.ga_client_id                    AS ga_client_id,
        s.utm_content                     AS stamped_ad_id,
        s.email_sha256                    AS session_email,
        min(s.started_at)                 AS first_seen_at
    FROM fact_web_session AS s
    WHERE s.fbclid != '' OR s.utm_content != ''
    GROUP BY fbclid, ga_client_id, stamped_ad_id, session_email
),
contacts AS (
    SELECT contact_id, email_sha256, fbclid, ga_client_id
    FROM fact_crm_contact
),
customers AS (
    SELECT DISTINCT stripe_customer, email_sha256
    FROM fact_payment
    WHERE email_sha256 != ''
)
SELECT
    se.fbclid                                                   AS fbclid,
    se.stamped_ad_id                                            AS ad_id,
    se.ga_client_id                                             AS ga_client_id,
    ifNull(c.contact_id, '')                                    AS contact_id,
    ifNull(cu.stripe_customer, '')                              AS stripe_customer,
    coalesce(nullIf(se.session_email, ''), c.email_sha256, '')   AS email_sha256,
    multiIf(
        se.fbclid != '' AND c.fbclid = se.fbclid, 'fbclid_passthrough',
        se.stamped_ad_id != '',                   'utm_content',
        'email_hash'
    )                                                            AS match_method,
    multiIf(
        se.fbclid != '' AND c.fbclid = se.fbclid, toFloat32(1.0),
        se.stamped_ad_id != '',                   toFloat32(0.9),
        toFloat32(0.6)
    )                                                            AS match_confidence,
    se.first_seen_at                                             AS first_seen_at
FROM sessions AS se
LEFT JOIN contacts  AS c  ON (c.fbclid != '' AND c.fbclid = se.fbclid)
                          OR (c.ga_client_id != '' AND c.ga_client_id = se.ga_client_id)
                          OR (se.session_email != '' AND c.email_sha256 = se.session_email)
LEFT JOIN customers AS cu ON cu.email_sha256 = coalesce(nullIf(se.session_email, ''), c.email_sha256);
