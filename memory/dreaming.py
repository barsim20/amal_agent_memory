"""
LangGraph Dreaming Pipeline:
- `memory_live_graph`: Live pass after each reply (adapter -> guardrails/tombstones/consent -> atomic save & notify).
- `memory_dream_graph`: Nightly consolidation across sessions (replay -> merge/supersede/confirm -> taxonomy evolution -> core profile rewrite -> privacy-preserving aggregation).
"""
from __future__ import annotations

import re
from typing import Any, TypedDict

from django.utils import timezone
from langgraph.graph import END, START, StateGraph

from .embeddings import cosine_similarity, trigram_similarity
from .guardrails import infer_category_and_slot
from .models import (
    MemoryCategoryLink,
    MemoryEvent,
    MemoryItem,
)
from .services import (
    compute_aggregate_insights,
    get_or_create_teacher,
    normalize_statement,
    regenerate_core_profile,
    save_or_update_memory,
    update_category_centroid,
)
from .taxonomy import run_taxonomy_evolution_for_teacher


class LiveGraphState(TypedDict, total=False):
    teacher_id: str
    surface: str
    product_area: str
    conversation_id: str
    message_id: str
    reflection_items: list[dict[str, Any] | str]
    core_profile: str
    enabled: bool
    adapted_candidates: list[dict[str, Any]]
    results: list[dict[str, Any]]


class DreamGraphState(TypedDict, total=False):
    teacher_id: str
    session_transcripts: list[dict[str, Any]]
    taxonomy_stage: str | None
    session_summary: str
    consolidation_stats: dict[str, int]
    taxonomy_result: dict[str, Any]
    core_profile_summary: str
    aggregate_stats: dict[str, Any]


def extract_atomic_statements_from_text(raw_text: str) -> list[dict[str, Any]]:
    """
    Lightweight rule + clause adapter that turns raw teacher message/reflection text
    into atomic candidate statements when structured reflection items are not pre-supplied.
    """
    if not raw_text or not raw_text.strip():
        return []

    clauses = [
        c.strip(" .")
        for c in re.split(r"(?:[.;\n]+|\b(?:and\s+i\s+also|also\s+i|pia\s+nina)\b)", raw_text)
        if c and c.strip(" .")
    ]
    extracted: list[dict[str, Any]] = []
    for clause in clauses:
        # Normalize first-person teacher statements into concise atomic third-person memory phrasing
        stmt = clause.strip()
        stmt = re.sub(r"^i\s+teach\b", "Teaches", stmt, flags=re.I)
        stmt = re.sub(r"^i\s+am\s+teaching\b", "Teaches", stmt, flags=re.I)
        stmt = re.sub(r"^i\s+prefer\b", "Prefers", stmt, flags=re.I)
        stmt = re.sub(r"^i\s+feel\b", "Feels", stmt, flags=re.I)
        stmt = re.sub(r"^i\s+co-?plan\b", "Co-plans", stmt, flags=re.I)
        stmt = re.sub(r"^i\s+completed\b", "Completed", stmt, flags=re.I)
        stmt = re.sub(r"^i\s+am\s+preparing\b", "Preparing", stmt, flags=re.I)
        stmt = re.sub(r"^we\s+have\s+no\b", "No", stmt, flags=re.I)
        stmt = re.sub(r"^i\s+have\s+no\b", "No", stmt, flags=re.I)
        stmt = re.sub(r"^my\s+class\s+has\b", "Has", stmt, flags=re.I)
        if stmt:
            stmt = stmt[0].upper() + stmt[1:]
            cat, sub, sens, _slot = infer_category_and_slot(stmt)
            extracted.append(
                {
                    "statement": stmt,
                    "category": cat,
                    "subcategory": sub,
                    "source": "stated",
                    "sensitivity": sens,
                    "confidence": 0.95,
                }
            )
    return extracted


# =============================================================================
# 1. LIVE PASS GRAPH (`memory_live_graph`)
# =============================================================================


def _live_load_profile_node(state: LiveGraphState) -> dict[str, Any]:
    teacher = get_or_create_teacher(state["teacher_id"])
    core_profile = teacher.core_profile.summary if hasattr(teacher, "core_profile") else ""
    return {
        "enabled": teacher.settings.enabled,
        "core_profile": core_profile,
    }


def _live_adapter_node(state: LiveGraphState) -> dict[str, Any]:
    """
    Adapter node (PRD line 136):
    Maps reflection output to the memory schema (content, category, subcategory, source,
    sensitivity, confidence, evidence message ids). Reuses fields the reflection already produces;
    fills only what is missing, and skips facts already present in the teacher's CoreProfile.
    """
    if not state.get("enabled", True):
        return {"adapted_candidates": []}

    raw_items = state.get("reflection_items") or []
    core_profile_norm = normalize_statement(state.get("core_profile") or "")
    adapted: list[dict[str, Any]] = []

    for item in raw_items:
        if isinstance(item, str):
            sub_items = extract_atomic_statements_from_text(item)
        elif isinstance(item, dict):
            sub_items = [item]
        else:
            continue

        for sub in sub_items:
            statement = (sub.get("statement") or sub.get("content") or "").strip()
            if not statement:
                continue

            # Skip if already known verbatim in CoreProfile
            norm_stmt = normalize_statement(statement)
            if norm_stmt and len(norm_stmt) > 6 and norm_stmt in core_profile_norm:
                continue

            cat_slug, sub_slug, inferred_sens, _slot = infer_category_and_slot(
                statement,
                explicit_category=sub.get("category"),
                explicit_subcategory=sub.get("subcategory"),
            )
            adapted.append(
                {
                    "statement": statement,
                    "category_slug": cat_slug,
                    "subcategory_slug": sub_slug,
                    "source": sub.get("source", "stated"),
                    "sensitivity": sub.get("sensitivity") or inferred_sens,
                    "confidence": float(sub.get("confidence", 0.95)),
                    "salience": float(sub.get("salience", 0.80)),
                    "message_id": sub.get("message_id") or state.get("message_id", "msg-1"),
                    "quote_span": sub.get("quote_span", "0:0"),
                }
            )

    return {"adapted_candidates": adapted}


def _live_persist_node(state: LiveGraphState) -> dict[str, Any]:
    if not state.get("enabled", True):
        return {"results": [{"saved": False, "status": "opted_out"}]}

    results: list[dict[str, Any]] = []
    for cand in state.get("adapted_candidates", []):
        res = save_or_update_memory(
            teacher_id=state["teacher_id"],
            statement=cand["statement"],
            category_slug=cand.get("category_slug"),
            subcategory_slug=cand.get("subcategory_slug"),
            source=cand.get("source", "stated"),
            confidence=cand.get("confidence", 0.95),
            salience=cand.get("salience", 0.80),
            surface=state.get("surface", "whatsapp"),
            product_area=state.get("product_area", "chat"),
            conversation_id=state.get("conversation_id", "conv-default"),
            message_id=cand.get("message_id", state.get("message_id", "msg-1")),
            quote_span=cand.get("quote_span", "0:0"),
            created_by="live_pass",
        )
        results.append(res)
    return {"results": results}


def build_memory_live_graph():
    builder = StateGraph(LiveGraphState)
    builder.add_node("load_profile", _live_load_profile_node)
    builder.add_node("adapter", _live_adapter_node)
    builder.add_node("persist", _live_persist_node)

    builder.add_edge(START, "load_profile")
    builder.add_edge("load_profile", "adapter")
    builder.add_edge("adapter", "persist")
    builder.add_edge("persist", END)
    return builder.compile()


memory_live_graph = build_memory_live_graph()


def invoke_live_pass(
    teacher_id: str,
    reflection_items: list[dict[str, Any] | str],
    surface: str = "whatsapp",
    product_area: str = "chat",
    conversation_id: str = "conv-default",
    message_id: str = "msg-1",
) -> dict[str, Any]:
    """Run `memory_live_graph` for a conversation turn's reflection output."""
    return memory_live_graph.invoke(
        {
            "teacher_id": teacher_id,
            "reflection_items": reflection_items,
            "surface": surface,
            "product_area": product_area,
            "conversation_id": conversation_id,
            "message_id": message_id,
        }
    )


# =============================================================================
# 2. NIGHTLY DREAMING GRAPH (`memory_dream_graph`)
# =============================================================================


def _dream_replay_sessions_node(state: DreamGraphState) -> dict[str, Any]:
    """
    Replay each session from the day as a short summary and ingest any uncaptured facts.
    """
    teacher = get_or_create_teacher(state["teacher_id"])
    if not teacher.settings.enabled:
        return {"session_summary": "Memory disabled by teacher."}

    transcripts = state.get("session_transcripts") or []
    summary_parts: list[str] = []
    for sess in transcripts:
        conv_id = sess.get("conversation_id", "conv-nightly")
        surface = sess.get("surface", "whatsapp")
        summary_text = sess.get("summary") or ""
        if summary_text:
            summary_parts.append(f"[{surface}:{conv_id}] {summary_text}")
        for stmt in sess.get("facts", []):
            if isinstance(stmt, str):
                save_or_update_memory(
                    teacher_id=teacher.teacher_id,
                    statement=stmt,
                    surface=surface,
                    conversation_id=conv_id,
                    created_by="dreaming",
                )
            elif isinstance(stmt, dict):
                save_or_update_memory(
                    teacher_id=teacher.teacher_id,
                    statement=stmt.get("statement", ""),
                    category_slug=stmt.get("category"),
                    subcategory_slug=stmt.get("subcategory"),
                    source=stmt.get("source", "stated"),
                    surface=surface,
                    conversation_id=conv_id,
                    created_by="dreaming",
                )

    return {"session_summary": " | ".join(summary_parts) if summary_parts else "Rehearsed active teacher memories."}


def _dream_consolidate_memories_node(state: DreamGraphState) -> dict[str, Any]:
    """
    Nightly consolidation (PRD lines 140-144):
    - Compares active memories within the same slot or high semantic similarity to merge/supersede/confirm.
    - Contradictions resolve to the newest stated fact; old one is kept as `superseded` with `retired_at` and `valid_to`.
    - Teacher edits (`created_by == 'teacher'`) always win over automated extraction.
    """
    teacher = get_or_create_teacher(state["teacher_id"])
    if not teacher.settings.enabled:
        return {"consolidation_stats": {"superseded": 0, "merged": 0, "confirmed": 0}}

    now = timezone.now()
    active_items = list(
        MemoryItem.objects.filter(teacher=teacher, status="active").order_by("-recorded_at")
    )

    superseded_count = 0
    merged_count = 0
    confirmed_count = 0
    retired_ids: set[str] = set()

    for i, newer in enumerate(active_items):
        if str(newer.id) in retired_ids:
            continue
        for j in range(i + 1, len(active_items)):
            older = active_items[j]
            if str(older.id) in retired_ids:
                continue

            sim = cosine_similarity(newer.embedding, older.embedding)
            trgm = trigram_similarity(newer.statement, older.statement)

            # Near-duplicate in same slot or very high semantic + lexical similarity -> merge/confirm into newest
            if sim >= 0.92 and trgm >= 0.65 and newer.sensitivity == older.sensitivity:
                keeper, loser = (older, newer) if (older.created_by == "teacher" and newer.created_by != "teacher") else (newer, older)
                loser.status = "superseded"
                loser.retired_at = now
                loser.valid_to = now
                loser.superseded_by = keeper
                loser.save(update_fields=["status", "retired_at", "valid_to", "superseded_by"])
                MemoryCategoryLink.objects.filter(memory=loser, valid_to__isnull=True).update(valid_to=now)

                keeper.salience = min(1.0, keeper.salience + 0.08)
                keeper.confidence = min(1.0, max(keeper.confidence, loser.confidence))
                keeper.save(update_fields=["salience", "confidence"])

                retired_ids.add(str(loser.id))
                merged_count += 1
                confirmed_count += 1
                continue

            # Contradiction in the same singleton/specific slot -> newest stated fact wins
            if (
                newer.slot == older.slot
                and newer.slot != "profile.identity"
                and not newer.slot.endswith(".general")
                and newer.source == "stated"
            ):
                if older.created_by == "teacher" and newer.created_by != "teacher":
                    winner, superseded_item = older, newer
                else:
                    winner, superseded_item = newer, older

                superseded_item.status = "superseded"
                superseded_item.retired_at = now
                superseded_item.valid_to = winner.valid_from or now
                superseded_item.superseded_by = winner
                superseded_item.save(update_fields=["status", "retired_at", "valid_to", "superseded_by"])
                MemoryCategoryLink.objects.filter(memory=superseded_item, valid_to__isnull=True).update(valid_to=now)

                retired_ids.add(str(superseded_item.id))
                superseded_count += 1

    # Refresh centroids on active categories
    for link in MemoryCategoryLink.objects.filter(
        memory__teacher=teacher,
        memory__status="active",
        valid_to__isnull=True,
    ).select_related("category"):
        update_category_centroid(link.category, teacher=teacher)

    return {
        "consolidation_stats": {
            "superseded": superseded_count,
            "merged": merged_count,
            "confirmed": confirmed_count,
        }
    }


def _dream_taxonomy_node(state: DreamGraphState) -> dict[str, Any]:
    res = run_taxonomy_evolution_for_teacher(
        teacher_id=state["teacher_id"],
        stage=state.get("taxonomy_stage"),
    )
    return {"taxonomy_result": res}


def _dream_rewrite_profile_node(state: DreamGraphState) -> dict[str, Any]:
    teacher = get_or_create_teacher(state["teacher_id"])
    profile = regenerate_core_profile(teacher)
    teacher.last_dreamed_at = timezone.now()
    teacher.save(update_fields=["last_dreamed_at"])

    MemoryEvent.objects.create(
        teacher=teacher,
        event="dreaming.nightly_completed",
        actor="memory_dream_graph",
        payload={
            "consolidation": state.get("consolidation_stats", {}),
            "taxonomy_changeset_id": state.get("taxonomy_result", {}).get("changeset_id"),
            "core_profile_version": profile.version,
        },
    )
    return {"core_profile_summary": profile.summary}


def _dream_aggregate_node(state: DreamGraphState) -> dict[str, Any]:
    agg = compute_aggregate_insights()
    return {"aggregate_stats": agg}


def build_memory_dream_graph():
    builder = StateGraph(DreamGraphState)
    builder.add_node("replay_sessions", _dream_replay_sessions_node)
    builder.add_node("consolidate_memories", _dream_consolidate_memories_node)
    builder.add_node("evolve_taxonomy", _dream_taxonomy_node)
    builder.add_node("rewrite_core_profile", _dream_rewrite_profile_node)
    builder.add_node("aggregate_insights", _dream_aggregate_node)

    builder.add_edge(START, "replay_sessions")
    builder.add_edge("replay_sessions", "consolidate_memories")
    builder.add_edge("consolidate_memories", "evolve_taxonomy")
    builder.add_edge("evolve_taxonomy", "rewrite_core_profile")
    builder.add_edge("rewrite_core_profile", "aggregate_insights")
    builder.add_edge("aggregate_insights", END)
    return builder.compile()


memory_dream_graph = build_memory_dream_graph()


def invoke_nightly_dream(
    teacher_id: str,
    session_transcripts: list[dict[str, Any]] | None = None,
    taxonomy_stage: str | None = None,
) -> dict[str, Any]:
    """Run `memory_dream_graph` for a teacher."""
    return memory_dream_graph.invoke(
        {
            "teacher_id": teacher_id,
            "session_transcripts": session_transcripts or [],
            "taxonomy_stage": taxonomy_stage,
        }
    )
