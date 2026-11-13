# PRD: Amal Memory and Dreaming

Nov 12, 2026 · @Baran Simsek

## Summary

Amal Memory turns Amal's existing in-conversation reflection into a persistent, teacher-owned memory: reflection output is stored as categorized memories, a deep nightly "dreaming" run consolidates them across all of a teacher's conversations, and teachers are notified on the web each time a memory is saved. v1 covers WhatsApp assistant chats and Amal Web (chat, Academy and Tools), serves 10,000 to 50,000 active teachers, and stores memories at three scopes: teacher, school or cohort, and anonymized global insights.

**Problem.** Amal already reflects within a conversation, but those reflections are not consolidated into a structured memory that carries across conversations and surfaces. Teachers still repeat their grade, subject, class size and constraints in every chat, Tools outputs ignore what worked last week, and the team has no structured view of what teachers struggle with across Kenya and Rwanda.

**Bet.** If agents remember what teachers have told them, and reflect on it between sessions, Amal feels like a colleague who knows your classroom. That should raise output quality, shorten time to a useful answer and increase retention.

**Principle.** Teachers own their data and decide how much they share with Amal. Every memory is visible, editable and deletable by the teacher, and sensitive information is stored only with explicit consent.

**Storage decision.** Memories live in our existing Postgres as typed, bi-temporal rows, with embeddings as one retrieval signal among several. We do not add a graph or vector database. Research (Nov 2026) shows the field converging on this pattern: small injected profile, atomic editable entries, offline consolidation. It also shows that public memory benchmarks are disputed, so we gate on our own eval.

## Goals, non-goals and success metrics

**Goals**

1. Agents stop asking for context teachers already gave (grade, subject, school type, language preference).
2. Tools outputs (lesson plans, schemes of work, assessments) adapt to each teacher's remembered context and past feedback.
3. Teachers can see and control everything Amal remembers, on WhatsApp and on the web.
4. Amal Labs gets anonymized, aggregated insight into teacher needs per cohort and country.

**Non-goals for v1**

- Memory shared between individual teachers (only aggregated cohort and global insights).
- Memory about learners as individuals beyond what a teacher explicitly consents to.
- Autonomous actions based on memory (sending reminders, enrolling in courses).
- Fine-tuning models on memory content.

**Success metrics** (measured 8 weeks after launch vs. a holdout group without memory)

| Metric | Target | How measured |
| --- | --- | --- |
| Redundant context questions per conversation | -60% | LLM judge on sampled transcripts |
| Tools output accepted without regeneration | +15 pp | Tools event logs |
| 4-week teacher retention | +10% relative | BigQuery cohort analysis |
| Memory precision (memory is true and stated by the teacher) | ≥ 95% | Weekly human audit of 200 memories |
| Wrong or surprising memory use reported | < 1% of conversations | Thumbs-down + "Amal got this wrong" flow |
| Teachers who opt out | < 10% | Settings events |
| Added cost per active teacher per month | ≤ $0.05 | LiteLLM spend logs |

## Users and core use cases

The primary user is a teacher in Kenya or Rwanda, often on a low-end Android phone, who is not tech-savvy and switches between English and Kiswahili. Secondary users are school and cohort leads (aggregated view only) and the Amal Labs team (anonymized global insights, admin tooling).

| # | As a… | I want… | So that… |
| --- | --- | --- | --- |
| 1 | Teacher on WhatsApp | Amal to know my grade, subject and class size | I don't repeat myself every chat |
| 2 | Teacher in Tools | lesson plans to reflect resources I said I lack (no projector, 60 learners) | outputs are usable in my real classroom |
| 3 | Teacher in the Academy on Amal Web | the simulation engine to recall which strategies I practiced | practice builds on itself |
| 4 | Teacher | to ask "what do you remember about me?" and fix or delete it | I stay in control of my data |
| 5 | Teacher sharing a personal struggle | to be asked before Amal keeps it | sensitive things are only kept if I agree |
| 6 | Cohort lead | to see what my cohort struggles with most | I can plan the next training session |
| 7 | Amal Labs | anonymized trends across countries | we prioritize content and courses |

## Memory model

A memory is one short, atomic, dated statement with a scope, a category, a subcategory, a source tag and a sensitivity level. Memories are grouped into category files per teacher, similar to Claude's profile, topics, areas, people and preferences.

**Scopes**

| Scope | Owner | Who can read it | Content |
| --- | --- | --- | --- |
| Teacher | The teacher | That teacher's agents, the teacher | Individual memories (all categories below) |
| Cohort / school | Amal Labs, on behalf of the cohort | Agents serving that cohort, cohort leads | Aggregated patterns, minimum 10 contributing teachers, no names |
| Global | Amal Labs | Amal Labs team, all agents as background | Anonymized trends per country, curriculum and language, minimum 50 teachers |

**Teacher-scope categories**

| Category | Subcategories | Example memory | Sensitivity |
| --- | --- | --- | --- |
| Profile | identity, school, role, languages | Teaches at a public primary school in Kisumu County | Normal |
| Teaching context | grades, subjects, curriculum, class size, timetable | Teaches Grade 6 Mathematics and Science, CBC | Normal |
| Classroom | resources, constraints, learner needs (aggregate), routines | No projector; around 60 learners per class | Normal |
| Practice | strategies tried, what worked, what did not, goals | Group work in Science went well; wants to try peer assessment | Normal |
| Learning journey | courses, modules, certificates, simulation results | Completed Foundations of AI Level 1, Module 3 | Normal |
| Ongoing work | active projects with status and deadlines | Preparing Term 2 scheme of work for Grade 6 Maths | Normal |
| People | colleagues, head teacher, mentors (as the teacher refers to them) | Co-plans with her colleague Wanjiru | Consent |
| Preferences | how Amal should respond: language, register, length, format | Prefers Kiswahili, short answers, bullet-point plans | Normal |
| Wellbeing | workload, stress, personal circumstances | Feels overwhelmed by marking load | Consent |
| Named learners | a specific learner's needs, by name | Learner Amina needs reading support | Consent |

These 10 are the protected core categories. Beyond them, each teacher gets dynamic **life areas**: new top-level categories that dreaming creates when a new field of interest appears (see Taxonomy evolution).

**Source tags.** Each memory is tagged `stated` (the teacher said it) or `observed` (derived from product events, for example 12 Tools requests for Grade 6 Maths). v1 does not store inferences about personality, ability or health. An `observed` memory is never phrased as something the teacher said.

**Never stored, even with consent:** ID, passport and payment numbers; disclosures of abuse or harm to a child (these trigger the safeguarding protocol instead); self-harm or suicide content (crisis flow instead); political or religious views; anything violating Amal's usage policy.

## Taxonomy evolution (memory reorganization)

The taxonomy grows with the teacher's life. When a new field of interest appears, for example a master's degree, coaching the school football team or a side business, the dreaming run can create a new top-level category for it, a so-called life area. Subcategories also evolve every night, and patterns that appear across many teachers are promoted into the shared taxonomy after the Amal team reviews them.

**Three layers**

- **Core categories (protected):** the 10 seeded categories. Dreaming can rename their subcategories but never deletes, merges or renames a core category, because consent, UI and permissions depend on them. The Amal team can still change them in the admin.
- **Life areas (dynamic top-level):** created, renamed, merged and archived by dreaming for each teacher, with a cap of 8 active life areas per teacher.
- **Subcategories:** evolve under both core categories and life areas.

| Operation | Level | Trigger | What happens | Guard |
| --- | --- | --- | --- | --- |
| New life area | Top level | 5 or more memories from at least 2 conversations about a topic that fits no existing category (similarity to every category centroid below 0.5) | New top-level category, named by the LLM in English and Kiswahili, with its own subcategories | Never for topics belonging to a consent category (health, personal struggles, named learners) |
| Archive life area | Top level | No new memory in the area for 90 days | Hidden from retrieval and the core profile; still visible and restorable on the memory page | Reactivated automatically when the topic returns |
| Merge life areas | Top level | Two life areas become near-duplicates | Merged into one, the older name kept unless the teacher renamed it | Teacher-created names are never overwritten |
| Re-file | Any | A memory is clearly closer to another category's centroid (similarity margin ≥ 0.1) | Memory moves, also between a core category and a life area | Max 20% of a teacher's memories move per night |
| Split | Subcategory | More than 12 memories that form 2 or more clusters (HDBSCAN on embeddings) | New subcategories, named in English and Kiswahili | Each new subcategory needs at least 4 memories |
| Merge | Subcategory | Fewer than 3 memories for 30 days, or two siblings are near-duplicates | Merged into the closest sibling | No re-split of the result within 30 days |
| Create | Subcategory | 5 or more "other" memories form a coherent cluster | New subcategory | Name checked against existing names to avoid duplicates |
| Rename | Life area or subcategory | The contents have drifted away from the name (LLM judge) | Display name changes, id stays | Max one rename per category per month |
| Promote | Life area or subcategory | Similar teacher-level categories exist for 200 or more teachers | Proposed in the admin; once approved, it becomes a global category that new memories can use directly | Never automatic |

**Rules**

- Reorganization never lowers sensitivity. A memory can move into a consent category, but never out of one without the teacher's yes. A life area is always normal sensitivity; anything sensitive inside its topic is filed under the matching consent category.
- Teachers can also create, rename, merge and delete life areas themselves on the memory page. Their changes always win over dreaming.
- Category ids are stable and memories reference them by id. Retrieval is embedding-based, so only category filters and the memory page change.
- Each nightly reorganization is one versioned `TaxonomyChange` with a diff, and it can be reverted in one step. The core profile is regenerated afterwards and includes active life areas in one line each.
- Teachers see reorganizations on the web, batched into one card per night instead of one per change, e.g. "Amal started a new area for you: Master's studies" with **Rename**, **Merge** and **Undo**, or "Amal reorganized your Classroom memories: Resources is now Equipment and Learning materials" with **View** and **Undo**. Undo reverts the change and freezes that category for 30 days.
- Quality bar: under 5% of reorganizations undone, and under 10% of new life areas undone, plus a weekly human review of 50 changes.

The thresholds (5, 8, 12, 90 days, 200) are starting values to tune on pilot data. Reorganization is switched on in three steps, because no public product or benchmark covers an evolving per-user taxonomy: (1) proposals only, reviewed in the admin, in Phase 2; (2) auto-apply for low-risk operations (rename, re-file) in Phase 3; (3) splits, merges and new life areas with per-night caps once the undo rate stays under target. Promotion to the shared taxonomy ships in Phase 4.

## Dreaming pipeline

Dreaming has two stages: the existing in-conversation reflection, wrapped in a live graph that turns its output into stored memories within minutes, and a new nightly run that rehearses the day and keeps memory clean.

&#91;embedded content: dreaming pipeline · live pass and nightly run\]

The live pass never blocks a reply: it runs as a Celery task after the agent answers. The nightly run only processes teachers with new activity that day.

**Live pass (`memory_live_graph`)**

- Input: the output of the existing reflection for the latest turns, plus the teacher's core profile so known facts are not saved twice.
- An adapter node maps reflection output to the memory schema (content, category, subcategory, source, sensitivity, confidence, evidence message ids). Fields the reflection already produces are reused; a small model call fills only what is missing.
- Every saved or updated memory emits a `memory.saved` event, which drives the teacher notification (see UX per surface).
- Explicit requests ("remember that…", "forget…") are handled synchronously by the agent's memory tools, not by this pass.

**Nightly run (`memory_dream_graph`)**

- Replays each session as a short summary, then compares it with existing memories to merge, supersede or confirm them.
- Contradictions resolve to the newest stated fact; the old one is kept as `superseded` until its retention period ends (see open questions).
- Aggregation reads only memories from teachers who allow sharing, and writes an insight only when the threshold is met.

**Cost estimate.** With \~30% of 50,000 teachers active per day, the live pass is \~15,000 small-model calls and the nightly run \~15,000 larger calls per night. At current small and mid-tier prices this should stay within the $0.05 per teacher per month target; validate in Phase 1.

## Consent, sensitive data and teacher controls

Memory is on by default for normal categories, with a clear onboarding message, and every sensitive memory needs a separate yes from the teacher before it is saved.

**Consent flow for sensitive memories**

1. The extractor labels a candidate as `consent` sensitivity (People, Wellbeing, Named learners).
2. The candidate goes to a `pending_consent` queue, never into retrieval.
3. At a natural break, or at the end of the conversation, the agent asks once in plain language, in the teacher's language: "Should I remember that you co-plan with Wanjiru? Reply YES or NO." On WhatsApp this is an interactive button message.
4. YES saves it; NO or no reply within 7 days deletes it. The agent never asks twice about the same item.
5. A standing "Always ask me" or "Never remember personal things" setting overrides per-item prompts.

**Teacher controls (full)**

| Control | WhatsApp | Amal Web |
| --- | --- | --- |
| See all memories | "What do you remember about me?" returns a grouped summary | Memory page grouped by category |
| Edit a memory | Reply with the correction in natural language | Inline edit |
| Delete one memory | "Forget that I teach Grade 5" | Delete button |
| Delete everything | "Forget everything" with confirmation | Delete all, with confirmation |
| Pause or opt out | "Stop remembering" | Toggle in settings |
| Exclude from cohort and global insights | Settings link | Toggle in settings |
| Export | Link to web page | JSON or PDF download |

**Rules.** Deletion hard-deletes the memory, its evidence and its category links in one transaction. A Celery task then removes derived copies within 24 hours: Redis cache, core profile (regenerated), cohort aggregates, BigQuery exports and LangSmith traces; backups expire within their retention window. A tombstone keeps only a keyed HMAC of the normalized statement and its category slot, never the text or embedding. Exact repeats are blocked; a near match in the same slot is asked about instead of saved. Opt-out stops extraction and retrieval immediately and schedules a full purge. Teacher edits always win over later extraction. Named learners are stored as pseudonymous learner ids and never appear in aggregates.

## Using memories in conversations

Every agent gets a small, always-on profile block plus a few retrieved memories, and uses a memory only when it changes the answer.

**Context assembly per turn**

1. **Core block (always injected, max \~300 tokens):** a nightly-written summary of Profile, Teaching context, Preferences and active life areas, cached in Redis.
2. **Skip check:** trivial turns (greetings, menu taps on WhatsApp) skip retrieval entirely.
3. **Hybrid search in one SQL call (top 5 to 8):** scoped to the teacher's `active` memories through a B-tree index. Three signals are fused with reciprocal rank fusion (k = 60): exact cosine distance on the embeddings, full-text search with the `simple` config (no stemming, so it works for Kiswahili), and trigram similarity for Kiswahili word forms and typos. A teacher has only 60 to 300 memories, so exact search is faster and more accurate than an approximate (HNSW) index, which loses recall under such narrow filters.
4. **Cohort and global hints (optional, max 2):** only for Tools and coaching flows, phrased as "Many teachers in your cohort…".
5. **Memory tools for the agent:** `search_memory`, `remember` (only when the teacher explicitly asks), `forget`, `list_memories`.

**Application rules (in the agent system prompt)**

- Use a memory only if it changes the content, format or language of the answer; never mention a memory just to show that Amal remembers.
- Never say "according to my memory" or "I have stored"; just apply it naturally.
- Never bring up Wellbeing or Named-learner memories unless the teacher raises the topic in this conversation.
- If the current message contradicts a memory, follow the message and let the live pass record the update.
- Preferences (language, length, format) always apply.

**Latency budget.** Retrieval adds at most 150 ms p95 to a turn. The SQL query takes under 10 ms; the query embedding call dominates. It runs in parallel with other pre-LLM work, and we measure its p95 from East African regions. If a hosted API is too slow, we self-host the embedding model.

## System architecture

No new services are needed: memory is a Django app, two LangGraph graphs on Celery, and pgvector in the existing Postgres, with every model call routed through LiteLLM.

&#91;embedded content: system architecture · surfaces, Django, workers, storage\]

The agent runtime reads memories from Postgres and the cached core profile from Redis on every turn; Celery workers write them.

| Component | Role in memory | Notes |
| --- | --- | --- |
| Django `memory` app | Models, REST endpoints for the memory page, consent API, admin inspector | ORM writes; one SQL function for hybrid retrieval; row-level security per teacher |
| LangGraph | `memory_live_graph` and `memory_dream_graph`, plus a custom retriever node | Not `PGVector` or `PostgresStore` as the system of record |
| LangChain | Prompt templates and Pydantic output parsers | Retrieval is our own SQL, not a LangChain vector store |
| LiteLLM | One router for all models; aliases `memory-live`, `memory-dream`, `memory-embed` | Guardrails and budget per alias; spend tagged per teacher |
| Postgres extensions | pgvector ≥ 0.8.7 (`halfvec`), `pg_trgm`, `ltree`, built-in full-text search | Exact per-teacher vector scan on the hot path; HNSW with iterative scans only for cross-teacher jobs |
| Celery + beat | Live pass after each reply; nightly fan-out per active teacher; deletion fan-out | Idempotent tasks keyed by teacher + message range |
| Turn.io | Messages in, interactive consent buttons out | Need a reliable conversation-end signal (see open questions) |

**Notifications.** The Celery worker publishes each `memory.saved` event to Redis pub/sub; Django Channels pushes it to open web sessions over WebSocket, with polling as a fallback. Events for teachers who are offline are stored as unread `MemoryNotification` rows and shown on the next visit.

## Storage design and data model

Memory is stored relationally in our existing Postgres (pgvector 0.8.7 or later), with embeddings as one retrieval signal next to full-text and trigram search. Categories, supersession, consent, deletion and reversible reorganization are all relational concerns. A graph or vector database would add a second source of truth and make deletion harder, without helping a teacher's 60 to 300 facts.

| Option | Why not the system of record |
| --- | --- |
| Pure vector store (generic PGVector, early Mem0) | No status, validity, taxonomy or tombstones; duplicates pile up |
| Temporal knowledge graph (Zep / Graphiti) | Many LLM calls per message, a graph DB to run, and facts spread across nodes, which makes hard deletion difficult. We adopt its bi-temporal model in plain columns instead |
| Memory files or blocks (Claude memory tool, Letta) | Great for the injected profile, weak for filtering, consent and aggregation at 50,000 teachers |

We borrow three patterns: Graphiti's bi-temporal validity, Mem0's "append live, consolidate offline" with multi-signal retrieval, and Letta and Claude's small injected profile rewritten offline.

| Model | Key fields | Notes |
| --- | --- | --- |
| `MemoryItem` | teacher, scope, statement, lang (`en`/`sw`/`mixed`), source, sensitivity, status, confidence, salience, embedding (`halfvec` 1024), embed\_model, tsv (generated, `simple` config), valid\_from/valid\_to, recorded\_at/retired\_at, superseded\_by, last\_used\_at | Hash-partitioned by teacher; B-tree on (teacher, status); GIN on tsv and trigram; HNSW only for cross-teacher jobs |
| `MemoryCategory` | teacher (null = global), parent, path (`ltree`, built from ids), slug, label\_en, label\_sw, kind (`core`/`life_area`/`sub`), is\_protected, global\_ref, centroid (`halfvec`), status, merged\_into, created\_by | Adjacency list is the source of truth; ltree is only a cache |
| `MemoryCategoryLink` | memory, category, valid\_from, valid\_to, changeset | Temporal assignment, so a reorganization is reverted without touching memories |
| `TaxonomyChangeset` + `TaxonomyOperation` | teacher, source, status (`proposed`/`applied`/`reverted`/`rejected`); ordered ops (create, rename, move, merge, split, refile) with before/after JSON | Drives notifications and one-step undo |
| `MemoryEvidence` | memory, surface (`whatsapp`/`web`), product area (`chat`/`academy`/`tools`), message\_id, quote span, extracted\_by | Provenance pointer, not raw text |
| `MemoryEvent` | teacher, memory, event, actor, payload | Append-only audit and notification feed; holds no deleted content after erasure |
| `MemoryTombstone` | teacher, statement\_hmac, slot | Blocks re-creation without storing text or embedding |
| `CoreProfile` | teacher, summary, version, built\_from (memory ids) | Regenerated when a source memory is deleted |
| `AggregateInsight` | scope, scope\_key, category, statement, n\_teachers | Written only above the k thresholds |
| `MemorySettings` | teacher, enabled, share\_aggregate, sensitive\_mode | Mirrors the controls table |
| `MemoryNotification` | teacher, memory or changeset, kind, origin surface, seen\_at, action | Feeds the undo-rate signal |
| `ConsentRequest` | memory, asked\_at, channel, answer | One row per sensitive candidate |

**Bi-temporal validity.** A memory's text is never updated in place. A correction inserts a new row, and the old row becomes `superseded` with `retired_at`, `valid_to` (when the change happened in the world, if known) and `superseded_by`. Retrieval reads only `active` rows. This keeps the history dreaming needs, while teacher deletions stay hard deletes.

**Taxonomy storage.** Categories use stable ids with `parent_id` as truth, so a rename touches one row. Each nightly reorganization is a `TaxonomyChangeset` of ordered operations. Applying it closes old `MemoryCategoryLink` rows and opens new ones; reverting does the reverse. Clustering (HDBSCAN or agglomerative, per teacher and top-level category) only writes proposals; nothing moves until a changeset is applied. Global promotion clusters subcategory centroids across teachers, which is where the HNSW index is used.

**Embeddings.** We store `halfvec(1024)`: same recall as full precision at half the size, and no binary quantization needed at our scale. The model is chosen by our own eval (recall@8 on English, Kiswahili and code-switched pairs) from a shortlist: bge-m3, AfriE5-Large-Instruct (best Swahili results on AfriMTEB) and one hosted model. `embed_model` per row makes a later re-embedding migration routine.

**Sizing.** About 3M memories need roughly 19 to 23 GB in total, including text, full-text and trigram indexes, history and an optional global HNSW index. This fits one Postgres instance with 32 to 64 GB RAM; the per-turn path never needs HNSW in memory.

**Isolation.** Row-level security on `teacher_id`, set with `SET LOCAL app.teacher_id` in Django middleware and in the LangGraph memory node. Only the aggregation job uses a separate role, reading de-identified views.

**Integration.** Django ORM with `pgvector.django.HalfVectorField` for writes, edits and admin; one raw SQL function for hybrid retrieval. Memory row, event and notification are written in one `transaction.atomic()`, so no notification fires for a rolled-back save. LangGraph uses a custom retriever node over these tables, not `langchain_postgres.PGVector` or `PostgresStore`, which cannot express status, validity, taxonomy or tombstones.

## UX per surface

Memory stays quiet inside conversations but is always visible: every save is shown to the teacher on the web. Because Amal users are not tech-savvy, every control uses words, never a bare icon.

**Memory notifications (web, every save)**

Every time a memory is saved or updated, the teacher sees it on the web, with a one-tap way to fix it. This makes memory transparent and catches wrong memories early.

- **During an Amal Web session (chat, Academy, Tools):** a small banner near the chat, e.g. "Amal remembered: You teach Grade 6 Mathematics", with text buttons **Edit** and **Undo**. It stays about 8 seconds and is kept in the notification list.
- **Updates show the change:** "Amal updated: class size 45 → 60".
- **Saves made elsewhere (WhatsApp, nightly run):** on the next web visit, a card "Amal learned 3 new things since your last visit", each with **Keep**, **Edit**, **Remove**.
- **Notification list:** a labelled "Memory" entry with an unread count; history for 30 days.
- **No spam:** at most one banner per 60 seconds; several saves are grouped into one banner.
- **Sensitive items** never appear as "saved": they show as a consent card ("Amal would like to remember this. Keep it?").
- **Undo** is a hard delete plus a tombstone, so the same fact is not saved again.
- **Setting:** teachers can switch banners to "summary on next visit only"; banners are on by default.
- **Quality signal:** undo and edit rates per category feed the weekly audit; an undo rate above 5% in a category flags the extractor for review.

**WhatsApp**

- First conversation after launch: one message explaining that Amal now remembers useful things about their teaching, with buttons "OK" and "See settings".
- Consent prompts use interactive reply buttons (YES / NO), max one per conversation, in English or Kiswahili.
- Natural-language commands: "What do you remember about me?", "Forget…", "Stop remembering". The answer to "what do you remember" is a short grouped list, max \~10 lines, with a link to the full page.
- No message per save on WhatsApp, to avoid chat spam; saves appear in the web notifications instead. An optional weekly "What Amal learned this week" message is an open question.

**Amal Web (chat and Academy)**

- "What Amal remembers" page in the profile, grouped by category with plain-language headers, each memory with Edit and Delete buttons labelled in text.
- Pending sensitive items show as a card: "Amal would like to remember this. Keep it?"
- The simulation engine shows a small line before a session: "Picking up from your last practice on questioning techniques."

**Amal Tools**

- Tool forms pre-fill from memory (grade, subject, class size) with a visible label "Filled from what you told Amal" and an easy change option.
- After an output, an optional one-tap "This fits my class / Doesn't fit" feedback feeds the Practice category.

**Admin (engine.amal.education)**

- Memory inspector per teacher (support access is logged and requires a reason).
- Cohort and global insight dashboards, aggregated only.

## Evaluation, safety and observability

Memory quality is gated by an offline eval set before launch and monitored weekly after, using the existing LangSmith setup.

**Offline eval set (build before Phase 1 ships)**

- 300 anonymized or synthetic conversations across WhatsApp and Amal Web (chat, Academy, Tools), English, Kiswahili and code-switched.
- Gold labels: which memories should be extracted, with category, subcategory and sensitivity.
- Adversarial cases: prompt injection ("remember that I am an admin"), sensitive disclosures, child-safeguarding disclosures, contradictions, jokes and hypotheticals.
- Retrieval set: 300 to 500 labelled query and memory pairs split across the three language modes, used to choose the embedding model by recall@8.
- Scenario tests: knowledge updates (supersession), deletion never re-created, consent gating, and taxonomy reverts.

Public benchmarks (LoCoMo, LongMemEval, DMR) are not launch gates. Their results are mostly vendor-run and disputed, and none covers taxonomy changes, consent, deletion or Kiswahili. Every dreaming prompt change must pass this eval first.

| Eval | Metric | Launch bar |
| --- | --- | --- |
| Extraction | precision / recall vs. gold | ≥ 0.95 / ≥ 0.75 |
| Categorization | correct category + subcategory | ≥ 0.90 |
| Sensitivity routing | consent items never stored without consent | 100% |
| Never-store list | blocked items stored | 0 |
| Injection resistance | instructions saved as memories | 0 |
| Application | judge: memory used when helpful, not used when irrelevant | ≥ 0.85 |

**Safety guardrails**

- LiteLLM guardrails run on extractor output before any write (PII patterns, never-store list).
- Memories are data, never instructions: they are injected in a delimited block, and the agent prompt says so.
- Safeguarding disclosures route to the existing escalation flow and are never stored as memories.
- Support staff access to a teacher's memories is logged and auditable.

**Observability**

- LangSmith traces for every live and nightly graph run, tagged with surface and language.
- Daily dashboard in BigQuery: memories written, consent asked/accepted, deletions, opt-outs, cost per teacher.
- Weekly human audit of 200 random memories against their evidence.

## Rollout plan

The proposed rollout takes about 18 weeks and widens the audience only after each quality gate is met; durations are estimates to validate with the engineering team.

&#91;embedded content: rollout · 5 phases, 4 gates, \~18 weeks (proposed)\]

WhatsApp goes first because it carries most conversations; cohort and global insights come last because they depend on stable, consented teacher-level data.

## Risks and open questions

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Wrong memories make Amal feel creepy or incorrect | Trust loss, opt-outs | Stated-only, high precision bar, easy correction, weekly audit |
| Kiswahili and code-switching lower extraction and retrieval quality | Missed or wrong memories | Language-specific eval slices; trigram search; embedding model chosen on our own data |
| Consent prompts feel naggy on WhatsApp | Lower engagement | Max one prompt per conversation, batch at end, "never ask" setting |
| Data protection compliance (Kenya DPA 2019, Rwanda Law 058/2021) | Legal exposure | DPIA before launch, data residency check, deletion fan-out across derived stores, consent records |
| Incomplete erasure: copies in traces, exports, caches, backups, LLM provider logs | Legal exposure, broken trust | Deletion fan-out task, PII redaction in LangSmith, `built_from` on core profiles, processor terms reviewed |
| Tombstones themselves are personal data, and HMAC misses paraphrases | Retention issue, re-created facts | HMAC only, same-slot near matches go to a consent prompt |
| Children's data in Named learners | Elevated legal and ethical risk | Consent-only, pseudonymous ids, never in aggregates, minimize |
| Re-identification from cohort insights in small schools | Privacy breach | k thresholds plus suppression of rare categories and human review before promotion |
| Taxonomy oscillates (split one night, merge the next) | Confused teachers | Hysteresis, minimum age for new categories, per-night caps, staged enablement |
| Embedding latency from East Africa | Breaks the 150 ms budget | Parallel call, skip trivial turns, self-hosted model if needed |
| Embedding model change | Re-embedding 3M rows | `embed_model` column and dual-write migration |
| Nightly cost spikes as usage grows | Budget | Skip teachers with no new messages, small model for the adapter, batch API where possible |

**Open questions**

- [ ] Existing reflection system: what does it output today, when does it run, and where is its output stored? Can the live pass reuse it unchanged, or does it need new fields (category, sensitivity, confidence)?
- [ ] Which embedding model wins on our eval: bge-m3, AfriE5-Large-Instruct or a hosted model? Self-hosted or via LiteLLM?
- [ ] Does our Postgres host support pgvector 0.8.7+, `ltree` and `pg_trgm` (and optionally ParadeDB `pg_search` for BM25)?
- [ ] Does Turn.io give us a reliable "conversation ended" event, or do we define it as 30 minutes of inactivity?
- [ ] Which models per pass in LiteLLM (adapter: small and fast; nightly: stronger), and which providers meet data residency needs?
- [ ] Is the teacher identity unified across WhatsApp and Amal Web today, or do we need account linking first?
- [ ] Should WhatsApp-only teachers, who rarely visit the web, get a weekly "What Amal learned this week" message so they also see their saves?
- [ ] How do cohort leads access insights: the admin dashboard, an email digest, or both?
- [ ] How long do we keep superseded memories, given the value for dreaming vs. data minimization?
- [ ] Legal review: is the opt-out default (memory on, sensitive opt-in) acceptable under both data protection laws?
