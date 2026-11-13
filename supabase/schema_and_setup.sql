-- =============================================================================
-- AMAL MEMORY & DREAMING — SUPABASE POSTGRESQL SETUP SCRIPT
-- =============================================================================
-- Target: Supabase PostgreSQL 15+ (500 MB Free Tier compatible)
-- Storage footprint for demo: ~3-6 KB per memory including indexes
--   -> 500 MB comfortably holds ~75,000 - 100,000 memories.
--
-- How to run:
--   1. Open your Supabase project -> SQL Editor -> New Query
--   2. Paste this entire script and click "Run"
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. Enable Required PostgreSQL Extensions
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector (includes halfvec(1024))
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- trigram similarity for Kiswahili & typos
CREATE EXTENSION IF NOT EXISTS ltree;      -- hierarchical materialized paths
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- UUID & HMAC helpers

-- -----------------------------------------------------------------------------
-- 2. Table 1: memory_teacherprofile
--    Unified teacher identity across WhatsApp and Amal Web
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_teacherprofile (
    teacher_id      VARCHAR(64) PRIMARY KEY,
    display_name    VARCHAR(128) NOT NULL DEFAULT '',
    phone_hash      VARCHAR(128) NOT NULL DEFAULT '',
    country         VARCHAR(32)  NOT NULL DEFAULT 'KE',
    cohort_key      VARCHAR(128) NOT NULL DEFAULT 'kisumu-cohort-1',
    curriculum      VARCHAR(64)  NOT NULL DEFAULT 'CBC',
    preferred_lang  VARCHAR(16)  NOT NULL DEFAULT 'en',
    last_active_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_dreamed_at TIMESTAMPTZ  NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- 3. Table 2: memory_memorycategory
--    Three-layer taxonomy: 'core' (10 protected), 'life_area' (cap 8), 'sub'
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_memorycategory (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    teacher_id      VARCHAR(64) NULL REFERENCES memory_teacherprofile(teacher_id) ON DELETE CASCADE,
    parent_id       UUID NULL REFERENCES memory_memorycategory(id) ON DELETE CASCADE,
    path             VARCHAR(512) NOT NULL DEFAULT '',
    path_ltree      ltree GENERATED ALWAYS AS (text2ltree( regexp_replace(coalesce(nullif(path, ''), 'root'), '[^A-Za-z0-9_.]', '_', 'g') )) STORED,
    slug            VARCHAR(128) NOT NULL,
    label_en        VARCHAR(128) NOT NULL,
    label_sw        VARCHAR(128) NOT NULL DEFAULT '',
    kind            VARCHAR(24)  NOT NULL DEFAULT 'core' CHECK (kind IN ('core', 'life_area', 'sub')),
    sensitivity     VARCHAR(16)  NOT NULL DEFAULT 'normal' CHECK (sensitivity IN ('normal', 'consent')),
    is_protected    BOOLEAN      NOT NULL DEFAULT FALSE,
    global_ref_id   UUID NULL REFERENCES memory_memorycategory(id) ON DELETE SET NULL,
    centroid        JSONB        NULL,
    centroid_vec    halfvec(1024) NULL,
    status          VARCHAR(24)  NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'merged', 'proposed_global')),
    merged_into_id  UUID NULL REFERENCES memory_memorycategory(id) ON DELETE SET NULL,
    created_by      VARCHAR(32)  NOT NULL DEFAULT 'system',
    last_renamed_at TIMESTAMPTZ  NULL,
    last_split_at   TIMESTAMPTZ  NULL,
    frozen_until    TIMESTAMPTZ  NULL,
    last_memory_at  TIMESTAMPTZ  NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memorycategory_teacher_kind_status
    ON memory_memorycategory (teacher_id, kind, status);
CREATE INDEX IF NOT EXISTS idx_memorycategory_slug_kind
    ON memory_memorycategory (slug, kind);
CREATE INDEX IF NOT EXISTS idx_memorycategory_path_ltree
    ON memory_memorycategory USING GIST (path_ltree);

-- -----------------------------------------------------------------------------
-- 4. Table 3: memory_memoryitem
--    Bi-temporal atomic memory row with halfvec(1024), 'simple' FTS, and pg_trgm
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_memoryitem (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    teacher_id           VARCHAR(64) NOT NULL REFERENCES memory_teacherprofile(teacher_id) ON DELETE CASCADE,
    scope                VARCHAR(16) NOT NULL DEFAULT 'teacher' CHECK (scope IN ('teacher', 'cohort', 'global')),
    statement            TEXT        NOT NULL,
    slot                 VARCHAR(128) NOT NULL DEFAULT 'general',
    learner_pseudonym_id VARCHAR(64) NOT NULL DEFAULT '',
    lang                 VARCHAR(12) NOT NULL DEFAULT 'en' CHECK (lang IN ('en', 'sw', 'mixed')),
    source               VARCHAR(16) NOT NULL DEFAULT 'stated' CHECK (source IN ('stated', 'observed')),
    sensitivity          VARCHAR(16) NOT NULL DEFAULT 'normal' CHECK (sensitivity IN ('normal', 'consent')),
    status               VARCHAR(24) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'pending_consent', 'superseded', 'archived')),
    confidence           DOUBLE PRECISION NOT NULL DEFAULT 0.95,
    salience             DOUBLE PRECISION NOT NULL DEFAULT 0.80,
    embedding            JSONB       NOT NULL DEFAULT '[]'::jsonb,
    embedding_halfvec    halfvec(1024) NULL,
    embed_model          VARCHAR(64) NOT NULL DEFAULT 'AfriE5-Large-Instruct-halfvec1024',
    tsv_tokens           TEXT        NOT NULL DEFAULT '',
    tsv                  tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(statement, ''))) STORED,
    valid_from           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to             TIMESTAMPTZ NULL,
    recorded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retired_at           TIMESTAMPTZ NULL,
    superseded_by_id     UUID NULL REFERENCES memory_memoryitem(id) ON DELETE SET NULL,
    last_used_at         TIMESTAMPTZ NULL,
    created_by           VARCHAR(32) NOT NULL DEFAULT 'live_pass'
);

-- Hot-path per-teacher B-tree indexes + GIN indexes on 'simple' tsvector and trigram statement
CREATE INDEX IF NOT EXISTS idx_memoryitem_teacher_status
    ON memory_memoryitem (teacher_id, status);
CREATE INDEX IF NOT EXISTS idx_memoryitem_teacher_slot_status
    ON memory_memoryitem (teacher_id, slot, status);
CREATE INDEX IF NOT EXISTS idx_memoryitem_tsv_gin
    ON memory_memoryitem USING GIN (tsv);
CREATE INDEX IF NOT EXISTS idx_memoryitem_statement_trgm_gin
    ON memory_memoryitem USING GIN (statement gin_trgm_ops);

-- Trigger to keep embedding_halfvec automatically synced when Django writes JSONB embedding
CREATE OR REPLACE FUNCTION sync_memoryitem_halfvec()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.embedding IS NOT NULL AND jsonb_typeof(NEW.embedding) = 'array' AND jsonb_array_length(NEW.embedding) = 1024 THEN
        NEW.embedding_halfvec := (NEW.embedding::text)::halfvec(1024);
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sync_memoryitem_halfvec ON memory_memoryitem;
CREATE TRIGGER trg_sync_memoryitem_halfvec
    BEFORE INSERT OR UPDATE OF embedding ON memory_memoryitem
    FOR EACH ROW EXECUTE FUNCTION sync_memoryitem_halfvec();

-- -----------------------------------------------------------------------------
-- 5. Table 4: memory_taxonomychangeset
--    Versioned nightly or manual reorganizations (one-step reversible)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_taxonomychangeset (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    teacher_id  VARCHAR(64) NULL REFERENCES memory_teacherprofile(teacher_id) ON DELETE CASCADE,
    source      VARCHAR(32)  NOT NULL DEFAULT 'dreaming',
    status      VARCHAR(16)  NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'applied', 'reverted', 'rejected')),
    summary_en  VARCHAR(255) NOT NULL DEFAULT '',
    summary_sw  VARCHAR(255) NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    applied_at  TIMESTAMPTZ  NULL,
    reverted_at TIMESTAMPTZ  NULL
);

CREATE INDEX IF NOT EXISTS idx_taxonomychangeset_teacher_status
    ON memory_taxonomychangeset (teacher_id, status);

-- -----------------------------------------------------------------------------
-- 6. Table 5: memory_taxonomyoperation
--    Ordered atomic operations inside a TaxonomyChangeset
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_taxonomyoperation (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    changeset_id       UUID NOT NULL REFERENCES memory_taxonomychangeset(id) ON DELETE CASCADE,
    seq                INTEGER NOT NULL DEFAULT 0,
    op_type            VARCHAR(32) NOT NULL,
    target_category_id UUID NULL REFERENCES memory_memorycategory(id) ON DELETE SET NULL,
    before_state       JSONB NOT NULL DEFAULT '{}'::jsonb,
    after_state        JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_taxonomyoperation_changeset_seq
    ON memory_taxonomyoperation (changeset_id, seq);

-- -----------------------------------------------------------------------------
-- 7. Table 6: memory_memorycategorylink
--    Temporal category assignment (closed & reopened on taxonomy changes)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_memorycategorylink (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id      UUID NOT NULL REFERENCES memory_memoryitem(id) ON DELETE CASCADE,
    category_id    UUID NOT NULL REFERENCES memory_memorycategory(id) ON DELETE CASCADE,
    subcategory_id UUID NULL REFERENCES memory_memorycategory(id) ON DELETE SET NULL,
    valid_from     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to       TIMESTAMPTZ NULL,
    changeset_id   UUID NULL REFERENCES memory_taxonomychangeset(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_memorycategorylink_memory_valid
    ON memory_memorycategorylink (memory_id, valid_to);
CREATE INDEX IF NOT EXISTS idx_memorycategorylink_category_valid
    ON memory_memorycategorylink (category_id, valid_to);

-- -----------------------------------------------------------------------------
-- 8. Table 7: memory_memoryevidence
--    Provenance pointer (surface, product_area, conversation_id, message_id, quote_span)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_memoryevidence (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id       UUID NOT NULL REFERENCES memory_memoryitem(id) ON DELETE CASCADE,
    surface         VARCHAR(16)  NOT NULL DEFAULT 'whatsapp' CHECK (surface IN ('whatsapp', 'web')),
    product_area    VARCHAR(16)  NOT NULL DEFAULT 'chat' CHECK (product_area IN ('chat', 'academy', 'tools')),
    conversation_id VARCHAR(128) NOT NULL DEFAULT 'conv-default',
    message_id      VARCHAR(128) NOT NULL DEFAULT 'msg-1',
    quote_span      VARCHAR(128) NOT NULL DEFAULT '0:0',
    extracted_by    VARCHAR(64)  NOT NULL DEFAULT 'memory_live_graph',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memoryevidence_memory
    ON memory_memoryevidence (memory_id);
CREATE INDEX IF NOT EXISTS idx_memoryevidence_conv
    ON memory_memoryevidence (conversation_id);

-- -----------------------------------------------------------------------------
-- 9. Table 8: memory_memoryevent
--    Append-only audit and notification event log (holds no deleted text)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_memoryevent (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    teacher_id    VARCHAR(64) NOT NULL REFERENCES memory_teacherprofile(teacher_id) ON DELETE CASCADE,
    memory_id_ref VARCHAR(64) NOT NULL DEFAULT '',
    event         VARCHAR(64) NOT NULL,
    actor         VARCHAR(64) NOT NULL DEFAULT 'system',
    payload       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memoryevent_teacher_created
    ON memory_memoryevent (teacher_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- 10. Table 9: memory_memorytombstone
--     Keyed HMAC of normalized statement + slot (never stores text or embedding)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_memorytombstone (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    teacher_id     VARCHAR(64)  NOT NULL REFERENCES memory_teacherprofile(teacher_id) ON DELETE CASCADE,
    statement_hmac VARCHAR(128) NOT NULL,
    slot           VARCHAR(128) NOT NULL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_memorytombstone_teacher_hmac UNIQUE (teacher_id, statement_hmac)
);

CREATE INDEX IF NOT EXISTS idx_memorytombstone_teacher_slot
    ON memory_memorytombstone (teacher_id, slot);

-- -----------------------------------------------------------------------------
-- 11. Table 10: memory_coreprofile
--     Always-injected compact (~300 tokens max) profile summary
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_coreprofile (
    teacher_id VARCHAR(64) PRIMARY KEY REFERENCES memory_teacherprofile(teacher_id) ON DELETE CASCADE,
    summary    TEXT        NOT NULL DEFAULT '',
    version    INTEGER     NOT NULL DEFAULT 1,
    built_from JSONB       NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- 12. Table 11: memory_aggregateinsight
--     Anonymized cohort (k >= 10) and global (k >= 50) insights
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_aggregateinsight (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope       VARCHAR(16)  NOT NULL CHECK (scope IN ('cohort', 'global')),
    scope_key   VARCHAR(128) NOT NULL,
    category_id UUID NOT NULL REFERENCES memory_memorycategory(id) ON DELETE CASCADE,
    statement   TEXT         NOT NULL,
    n_teachers  INTEGER      NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aggregateinsight_scope_key
    ON memory_aggregateinsight (scope, scope_key);

-- -----------------------------------------------------------------------------
-- 13. Table 12: memory_memorysettings
--     Teacher-owned memory controls and consent preferences
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_memorysettings (
    teacher_id         VARCHAR(64) PRIMARY KEY REFERENCES memory_teacherprofile(teacher_id) ON DELETE CASCADE,
    enabled            BOOLEAN     NOT NULL DEFAULT TRUE,
    share_aggregate    BOOLEAN     NOT NULL DEFAULT TRUE,
    sensitive_mode     VARCHAR(24) NOT NULL DEFAULT 'always_ask' CHECK (sensitive_mode IN ('always_ask', 'never_remember')),
    banner_mode        VARCHAR(24) NOT NULL DEFAULT 'realtime' CHECK (banner_mode IN ('realtime', 'next_visit_summary')),
    whatsapp_onboarded BOOLEAN     NOT NULL DEFAULT FALSE,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- 14. Table 13: memory_memorynotification
--     Web notification banners, consent cards, and nightly reorganization cards
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_memorynotification (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    teacher_id     VARCHAR(64)  NOT NULL REFERENCES memory_teacherprofile(teacher_id) ON DELETE CASCADE,
    memory_id      UUID NULL REFERENCES memory_memoryitem(id) ON DELETE SET NULL,
    changeset_id   UUID NULL REFERENCES memory_taxonomychangeset(id) ON DELETE SET NULL,
    category_slug  VARCHAR(128) NOT NULL DEFAULT '',
    kind           VARCHAR(24)  NOT NULL DEFAULT 'saved' CHECK (kind IN ('saved', 'updated', 'consent_prompt', 'taxonomy_change')),
    title          VARCHAR(255) NOT NULL,
    body           TEXT         NOT NULL DEFAULT '',
    diff_before    TEXT         NOT NULL DEFAULT '',
    diff_after     TEXT         NOT NULL DEFAULT '',
    origin_surface VARCHAR(16)  NOT NULL DEFAULT 'web',
    grouped_count  INTEGER      NOT NULL DEFAULT 1,
    grouped_items  JSONB        NOT NULL DEFAULT '[]'::jsonb,
    seen_at        TIMESTAMPTZ  NULL,
    action         VARCHAR(16)  NOT NULL DEFAULT 'pending' CHECK (action IN ('pending', 'kept', 'edited', 'undone', 'removed')),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memorynotification_teacher_created
    ON memory_memorynotification (teacher_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- 15. Table 14: memory_consentrequest
--     Pending consent queue for sensitive candidate memories (7-day expiry)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_consentrequest (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    teacher_id     VARCHAR(64)  NOT NULL REFERENCES memory_teacherprofile(teacher_id) ON DELETE CASCADE,
    memory_id      UUID NULL UNIQUE REFERENCES memory_memoryitem(id) ON DELETE CASCADE,
    statement_hmac VARCHAR(128) NOT NULL,
    slot           VARCHAR(128) NOT NULL,
    prompt_text    TEXT         NOT NULL,
    asked_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at     TIMESTAMPTZ  NOT NULL DEFAULT (NOW() + INTERVAL '7 days'),
    channel        VARCHAR(16)  NOT NULL DEFAULT 'whatsapp',
    answer         VARCHAR(16)  NOT NULL DEFAULT 'pending' CHECK (answer IN ('pending', 'yes', 'no', 'expired')),
    answered_at    TIMESTAMPTZ  NULL
);

CREATE INDEX IF NOT EXISTS idx_consentrequest_teacher_answer
    ON memory_consentrequest (teacher_id, answer);
CREATE INDEX IF NOT EXISTS idx_consentrequest_teacher_hmac
    ON memory_consentrequest (teacher_id, statement_hmac);

-- -----------------------------------------------------------------------------
-- 16. Hybrid Search SQL Function (Reciprocal Rank Fusion k = 60)
--     Fuses exact halfvec(1024) cosine similarity, 'simple' FTS, and pg_trgm
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION amal_hybrid_search_rrf(
    p_teacher_id VARCHAR(64),
    p_query_text TEXT,
    p_query_vec  halfvec(1024),
    p_top_k      INTEGER DEFAULT 8,
    p_rrf_k      INTEGER DEFAULT 60
)
RETURNS TABLE (
    id          UUID,
    statement   TEXT,
    slot        VARCHAR(128),
    lang        VARCHAR(12),
    source      VARCHAR(16),
    sensitivity VARCHAR(16),
    confidence  DOUBLE PRECISION,
    salience    DOUBLE PRECISION,
    cosine_sim  DOUBLE PRECISION,
    fts_score   DOUBLE PRECISION,
    trgm_score  DOUBLE PRECISION,
    rrf_score   DOUBLE PRECISION
) LANGUAGE sql STABLE AS $$
    WITH active_memories AS (
        SELECT
            m.id,
            m.statement,
            m.slot,
            m.lang,
            m.source,
            m.sensitivity,
            m.confidence,
            m.salience,
            CASE
                WHEN m.embedding_halfvec IS NOT NULL THEN 1.0 - (m.embedding_halfvec <=> p_query_vec)
                ELSE 0.0
            END AS cosine_sim,
            ts_rank_cd(m.tsv, plainto_tsquery('simple', p_query_text))::double precision AS fts_score,
            similarity(m.statement, p_query_text)::double precision AS trgm_score
        FROM memory_memoryitem m
        WHERE m.teacher_id = p_teacher_id
          AND m.status = 'active'
    ),
    ranked AS (
        SELECT
            *,
            ROW_NUMBER() OVER (ORDER BY cosine_sim DESC) AS r_vec,
            ROW_NUMBER() OVER (ORDER BY fts_score DESC, cosine_sim DESC) AS r_fts,
            ROW_NUMBER() OVER (ORDER BY trgm_score DESC, cosine_sim DESC) AS r_trgm
        FROM active_memories
    )
    SELECT
        id,
        statement,
        slot,
        lang,
        source,
        sensitivity,
        confidence,
        salience,
        cosine_sim,
        fts_score,
        trgm_score,
        (1.0 / (p_rrf_k + r_vec)) +
        (1.0 / (p_rrf_k + r_fts)) +
        (1.0 / (p_rrf_k + r_trgm)) AS rrf_score
    FROM ranked
    ORDER BY rrf_score DESC
    LIMIT p_top_k;
$$;

-- -----------------------------------------------------------------------------
-- 17. Row-Level Security (RLS) Policies per Teacher (`app.teacher_id`)
--     Allows either matching `current_setting('app.teacher_id', true)` OR
--     when `app.teacher_id` is not set (for Django admin/migrations).
-- -----------------------------------------------------------------------------
ALTER TABLE memory_memoryitem ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_teacher_memoryitem ON memory_memoryitem;
CREATE POLICY rls_teacher_memoryitem ON memory_memoryitem
    USING (
        nullif(current_setting('app.teacher_id', true), '') IS NULL
        OR teacher_id = current_setting('app.teacher_id', true)
    );

ALTER TABLE memory_memorytombstone ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_teacher_tombstone ON memory_memorytombstone;
CREATE POLICY rls_teacher_tombstone ON memory_memorytombstone
    USING (
        nullif(current_setting('app.teacher_id', true), '') IS NULL
        OR teacher_id = current_setting('app.teacher_id', true)
    );

ALTER TABLE memory_consentrequest ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_teacher_consent ON memory_consentrequest;
CREATE POLICY rls_teacher_consent ON memory_consentrequest
    USING (
        nullif(current_setting('app.teacher_id', true), '') IS NULL
        OR teacher_id = current_setting('app.teacher_id', true)
    );

COMMIT;
