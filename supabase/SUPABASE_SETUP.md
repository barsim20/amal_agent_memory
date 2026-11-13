# Supabase Setup Guide for Amal Memory & Dreaming (500 MB Free Tier)

## 1. Storage Sizing on the 500 MB Free Tier

Each teacher memory (`MemoryItem` + `MemoryCategoryLink` + `MemoryEvidence` + `halfvec(1024)` vector + `tsv` + `pg_trgm` index entries) uses **~4 to 6 KB**:
- `halfvec(1024)` is 2 bytes per dimension = **2 KB per memory** (half the size of standard `vector(1024)`).
- Text, metadata, `tsvector`, and `pg_trgm` indexes add **~2–4 KB per memory**.
- **Capacity on 500 MB**: **~75,000 to 100,000 active & historical memories** (or ~500–1,000 heavily active teachers), which is more than enough for this demo and pilot phase.
- Because retrieval runs an exact per-teacher scan filtered by `B-tree (teacher_id, status)`, we **do not** build a heavy global HNSW index on `memory_memoryitem`, saving ~40% of vector index storage.

---

## 2. Step-by-Step Setup in Supabase

### Step 1: Create or Open Your Supabase Project
1. Go to [https://supabase.com/dashboard](https://supabase.com/dashboard) and open your project.
2. Click **Connect** in the top bar -> copy the **Session Pooler** URI (port `5432`), which looks like:
   ```text
   postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```
   *(Use Port `5432` Session mode rather than Port `6543` Transaction mode so Django migrations and `SET LOCAL app.teacher_id` Row-Level Security work seamlessly).*

### Step 2: Option A — Run the SQL Setup Script in Supabase SQL Editor (Fastest)
1. In the Supabase Dashboard sidebar, open **SQL Editor** -> **New query**.
2. Copy and paste the contents of [`supabase/schema_and_setup.sql`](schema_and_setup.sql) and click **Run**.
3. Then mark Django's initial migration as applied (or run `migrate --fake-initial`):
   ```bash
   export DATABASE_URL="postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require"
   .venv/bin/python manage.py migrate --fake-initial
   ```

### Step 2: Option B — Let Django Migrations Create the Tables
1. Enable the extensions in **Supabase SQL Editor**:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   CREATE EXTENSION IF NOT EXISTS ltree;
   CREATE EXTENSION IF NOT EXISTS pgcrypto;
   ```
2. Set `DATABASE_URL` and run Django's `migrate`:
   ```bash
   export DATABASE_URL="postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require"
   .venv/bin/python manage.py migrate
   ```
3. Run [`supabase/schema_and_setup.sql`](schema_and_setup.sql) in the SQL Editor afterwards to add the `halfvec(1024)` sync trigger, `GIN` trigram/FTS indexes, `amal_hybrid_search_rrf` SQL function, and Row-Level Security policies.

---

## 3. Summary of All 14 Tables Created

| # | Table Name | Purpose | Key Columns & Indexes |
|---|---|---|---|
| 1 | `memory_teacherprofile` | Unified teacher identity across WhatsApp & Web | `teacher_id` (PK), `country`, `cohort_key`, `curriculum`, `last_active_at`, `last_dreamed_at` |
| 2 | `memory_memorycategory` | 3-layer taxonomy (`core`, `life_area`, `sub`) | `id` (UUID PK), `teacher_id`, `parent_id`, `path`, `path_ltree` (GIST), `kind`, `sensitivity`, `is_protected`, `centroid`, `frozen_until` |
| 3 | `memory_memoryitem` | Bi-temporal atomic teacher memories | `id` (UUID PK), `teacher_id`, `statement`, `slot`, `source`, `sensitivity`, `status`, `embedding_halfvec halfvec(1024)`, `tsv` (GIN `simple`), `valid_from`/`valid_to`, `recorded_at`/`retired_at`, `superseded_by_id` |
| 4 | `memory_memorycategorylink` | Temporal category assignment (`valid_from`, `valid_to`) | `memory_id`, `category_id`, `subcategory_id`, `valid_from`, `valid_to`, `changeset_id` |
| 5 | `memory_taxonomychangeset` | Versioned nightly reorganization batch | `id` (UUID PK), `teacher_id`, `status` (`proposed`/`applied`/`reverted`/`rejected`), `summary_en`, `summary_sw` |
| 6 | `memory_taxonomyoperation` | Ordered atomic ops inside a changeset | `changeset_id`, `seq`, `op_type`, `target_category_id`, `before_state` (JSONB), `after_state` (JSONB) |
| 7 | `memory_memoryevidence` | Provenance pointer to conversation message | `memory_id`, `surface` (`whatsapp`/`web`), `product_area`, `conversation_id`, `message_id`, `quote_span` |
| 8 | `memory_memoryevent` | Append-only audit feed (holds no deleted text) | `teacher_id`, `memory_id_ref`, `event`, `actor`, `payload` (JSONB), `created_at` |
| 9 | `memory_memorytombstone` | Keyed HMAC-SHA256 of deleted/declined statements | `teacher_id`, `statement_hmac` (UNIQUE with `teacher_id`), `slot` |
| 10 | `memory_coreprofile` | Compact (~300 tokens) always-injected summary | `teacher_id` (PK), `summary`, `version`, `built_from` (JSONB list of memory UUIDs) |
| 11 | `memory_aggregateinsight` | Anonymized cohort ($k \ge 10$) & global ($k \ge 50$) insights | `scope`, `scope_key`, `category_id`, `statement`, `n_teachers` |
| 12 | `memory_memorysettings` | Teacher opt-out, aggregate sharing & consent settings | `teacher_id` (PK), `enabled`, `share_aggregate`, `sensitive_mode`, `banner_mode` |
| 13 | `memory_memorynotification` | Web save banners, consent cards & taxonomy cards | `teacher_id`, `memory_id`, `changeset_id`, `kind`, `title`, `grouped_count`, `action`, `seen_at` |
| 14 | `memory_consentrequest` | Pending consent queue for sensitive memories | `id` (UUID PK), `teacher_id`, `memory_id`, `statement_hmac`, `slot`, `prompt_text`, `expires_at`, `answer` |
