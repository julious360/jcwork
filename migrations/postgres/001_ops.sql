-- Operational state. Postgres, not ClickHouse, because these writes must be
-- transactional: "I paused ad X" must be recorded exactly once, and an idempotency
-- key must be atomically claimable. ClickHouse cannot promise either.

CREATE TABLE IF NOT EXISTS jobs (
    id            BIGSERIAL PRIMARY KEY,
    kind          TEXT        NOT NULL,
    payload       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    status        TEXT        NOT NULL DEFAULT 'pending',
    attempts      INT         NOT NULL DEFAULT 0,
    max_attempts  INT         NOT NULL DEFAULT 3,
    last_error    TEXT,
    run_after     TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_at     TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT jobs_status_check
        CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'dead'))
);

CREATE INDEX IF NOT EXISTS jobs_claim_idx
    ON jobs (status, run_after) WHERE status = 'pending';


-- The audit ledger. Every decision the agent makes lands here with the exact
-- metrics that justified it, so a past decision can be re-litigated against the
-- numbers the agent actually saw rather than how they look today.
CREATE TABLE IF NOT EXISTS agent_actions (
    id                BIGSERIAL PRIMARY KEY,
    run_id            UUID        NOT NULL,
    action_type       TEXT        NOT NULL,
    status            TEXT        NOT NULL DEFAULT 'proposed',
    ad_id             TEXT,
    adset_id          TEXT,
    campaign_id       TEXT,
    reason            TEXT        NOT NULL,
    metrics_snapshot  JSONB       NOT NULL DEFAULT '{}'::jsonb,
    params            JSONB       NOT NULL DEFAULT '{}'::jsonb,
    dry_run           BOOLEAN     NOT NULL DEFAULT TRUE,
    idempotency_key   TEXT,
    meta_response     JSONB,
    error             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    executed_at       TIMESTAMPTZ,
    CONSTRAINT agent_actions_status_check
        CHECK (status IN ('proposed', 'awaiting_approval', 'approved',
                          'executed', 'verified', 'failed', 'skipped'))
);

CREATE INDEX IF NOT EXISTS agent_actions_run_idx  ON agent_actions (run_id);
CREATE INDEX IF NOT EXISTS agent_actions_ad_idx   ON agent_actions (ad_id, created_at DESC);
-- Supports the daily action cap without scanning history.
CREATE INDEX IF NOT EXISTS agent_actions_exec_idx ON agent_actions (executed_at)
    WHERE status IN ('executed', 'verified');


-- Claimed BEFORE a mutation is sent. If the process dies mid-flight, the retry
-- finds the key already present and refuses to double-create an ad or re-apply a
-- budget increase.
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key         TEXT PRIMARY KEY,
    action_id   BIGINT REFERENCES agent_actions (id) ON DELETE CASCADE,
    result      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- Persisted so a restart cannot stampede an ad account that is still recovering.
-- An in-memory breaker resets to "closed" on deploy, which is exactly when you
-- least want a burst of writes.
CREATE TABLE IF NOT EXISTS circuit_breaker (
    name            TEXT PRIMARY KEY,
    state           TEXT        NOT NULL DEFAULT 'closed',
    failure_count   INT         NOT NULL DEFAULT 0,
    opened_at       TIMESTAMPTZ,
    reopen_after    TIMESTAMPTZ,
    last_reason     TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT circuit_breaker_state_check
        CHECK (state IN ('closed', 'open', 'half_open'))
);


CREATE TABLE IF NOT EXISTS creative_assets (
    id                 BIGSERIAL PRIMARY KEY,
    asset_type         TEXT        NOT NULL,
    dna_id             TEXT        NOT NULL,
    concept_family_id  TEXT        NOT NULL,
    pain_point_id      TEXT,
    local_path         TEXT,
    remote_url         TEXT,
    copy               JSONB       NOT NULL DEFAULT '{}'::jsonb,
    validation         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    status             TEXT        NOT NULL DEFAULT 'draft',
    published_ad_id    TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT creative_assets_status_check
        CHECK (status IN ('draft', 'validated', 'rejected', 'needs_review', 'published'))
);

CREATE INDEX IF NOT EXISTS creative_assets_dna_idx ON creative_assets (dna_id);


-- The entropy reservoir: creative genes harvested from outside our own account.
CREATE TABLE IF NOT EXISTS dna_pool (
    id            BIGSERIAL PRIMARY KEY,
    source        TEXT        NOT NULL,   -- ad_library | youtube | podcast | internal
    source_ref    TEXT,
    hook_type     TEXT,
    visual_motif  TEXT,
    cta_style     TEXT,
    raw_excerpt   TEXT,
    embedding     DOUBLE PRECISION[],
    is_external   BOOLEAN     NOT NULL DEFAULT TRUE,
    used_count    INT         NOT NULL DEFAULT 0,
    content_hash  TEXT        NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT dna_pool_hash_unique UNIQUE (content_hash)
);


-- Concepts we have actually shipped. The novelty gate scores candidates against
-- this history; without it the agent converges on its own past winners.
CREATE TABLE IF NOT EXISTS shipped_concepts (
    id                 BIGSERIAL PRIMARY KEY,
    dna_id             TEXT        NOT NULL,
    concept_family_id  TEXT        NOT NULL,
    summary            TEXT        NOT NULL,
    embedding          DOUBLE PRECISION[] NOT NULL,
    is_external_dna    BOOLEAN     NOT NULL DEFAULT FALSE,
    shipped_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS shipped_concepts_time_idx ON shipped_concepts (shipped_at DESC);


CREATE TABLE IF NOT EXISTS research_cache (
    content_hash  TEXT PRIMARY KEY,
    category      TEXT        NOT NULL,
    provider      TEXT        NOT NULL,
    report        JSONB       NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
