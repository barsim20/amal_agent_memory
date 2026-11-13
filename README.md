# Amal Memory and Dreaming

Implementation of [PRD_Amal_Memory_and_Dreaming.md](PRD_Amal_Memory_and_Dreaming.md): persistent, teacher-owned memory across WhatsApp and Amal Web with bi-temporal relational storage, 3-signal hybrid retrieval, LangGraph live & nightly dreaming pipelines, and a 3-layer evolving taxonomy.

## Architecture Overview

1. **Django `memory` App (`memory/`)**
   - **Models (`memory/models.py`)**:
     - `TeacherProfile`: Unified teacher identity across WhatsApp and Amal Web.
     - `MemoryCategory`: Three-layer taxonomy (`core` protected categories, dynamic per-teacher `life_area` categories capped at 8 active, and `sub` subcategories) with materialized `ltree`-compatible `path` and 1024-dim `halfvec` centroids.
     - `MemoryItem`: Bi-temporal memory rows (`valid_from`, `valid_to`, `recorded_at`, `retired_at`, `superseded_by`) with `halfvec(1024)` embeddings, `simple` FTS tokens, source tags (`stated` / `observed`), and sensitivity (`normal` / `consent`).
     - `MemoryCategoryLink`: Temporal category assignments (`valid_from`, `valid_to`, `changeset`) enabling one-step reorganization reverts without mutating `MemoryItem` rows.
     - `TaxonomyChangeset` & `TaxonomyOperation`: Versioned nightly or manual reorganizations (`create_life_area`, `archive_life_area`, `merge_life_areas`, `refile`, `split_subcategory`, `merge_subcategory`, `create_subcategory`, `rename`, `promote`).
     - `MemoryEvidence`: Provenance pointer (`surface`, `product_area`, `conversation_id`, `message_id`, `quote_span`).
     - `MemoryEvent`: Append-only audit feed holding no deleted text after erasure.
     - `MemoryTombstone`: Keyed HMAC-SHA256 of normalized statement + semantic slot (never raw text or embeddings) blocking exact repeats and routing same-slot near-matches to consent.
     - `CoreProfile`: Compact (~300 tokens max) summary of `Profile`, `Teaching context`, `Preferences`, and active `Life areas`, cached in Redis and regenerated whenever a `built_from` source memory is edited or deleted.
     - `AggregateInsight`: Privacy-preserving cohort ($k \ge 10$) and global ($k \ge 50$) insights.
     - `MemorySettings`, `MemoryNotification`, `ConsentRequest`.

2. **Dreaming Pipeline (`memory/dreaming.py` & `memory/tasks.py`)**
   - **Live Pass (`memory_live_graph`)**: Runs asynchronously on Celery (`run_live_memory_pass`, idempotent per teacher + message range). Loads the teacher's `CoreProfile` to avoid duplicate saves, maps reflection outputs to the memory schema, runs safety & never-store guardrails, checks HMAC tombstones, routes sensitive categories (`People`, `Wellbeing`, `Named learners`) to `pending_consent`, and writes `MemoryItem` + `MemoryCategoryLink` + `MemoryEvidence` + `MemoryEvent` + `MemoryNotification` atomically.
   - **Nightly Run (`memory_dream_graph`)**: Triggered by Celery beat (`run_nightly_dream_fanout`) only for teachers with new activity since `last_dreamed_at`. Replays session summaries, merges near-duplicates, resolves contradictions to the newest stated fact (preserving teacher edits), runs Taxonomy Evolution, rewrites `CoreProfile`, and computes `AggregateInsight` rows.

3. **Taxonomy Evolution (`memory/taxonomy.py`)**
   - Supports creating dynamic Life Areas ($\ge 5$ memories across $\ge 2$ conversations with centroid similarity $< 0.50$, never for consent topics, max 8 active), archiving after 90 days of inactivity (and auto-reactivating when the topic returns), merging near-duplicate life areas (preserving teacher-defined names), re-filing memories closer to another centroid by margin $\ge 0.10$ (capped at 20% of memories per night, never lowering sensitivity), splitting subcategories ($>12$ memories forming $\ge 2$ clusters of $\ge 4$ memories), and one-step **Undo** (`undo_taxonomy_changeset`) which restores previous `MemoryCategoryLink` rows and freezes affected categories for 30 days.

4. **Hybrid Retrieval & Per-Turn Context Assembly (`memory/retrieval.py`)**
   - Skips retrieval on trivial turns (greetings, WhatsApp menu taps).
   - Fuses 3 signals with Reciprocal Rank Fusion ($k = 60$):
     1. Exact cosine similarity on `halfvec(1024)` embeddings
     2. Un-stemmed `simple` full-text search (supporting English, Kiswahili, and code-switching)
     3. Character trigram similarity (`pg_trgm`)
   - Enforces application rules (never injecting `Wellbeing` or `Named learners` memories unless raised by the teacher in the current turn; wrapping memories in `<teacher_memory_data>` as data rather than instructions).

5. **Simple Functional Categorical Web UI (`memory/templates/memory/dashboard.html`)**
   - Displays the Core Profile block, Dynamic Life Areas, the 10 Protected Core Categories with subcategory badges, Bi-Temporal Superseded History & Tombstone counts, Live Save Banners (grouped within 60s), Pending Consent Cards, Nightly Taxonomy Reorganization Cards, and interactive simulators for the Live Pass, Nightly Dreaming, and Hybrid Retrieval.

## Quick Start

```bash
# Run migrations
.venv/bin/python manage.py migrate

# Run the test suite
.venv/bin/pytest

# Start the development server
.venv/bin/python manage.py runserver 0.0.0.0:8000
```
