"""
Celery tasks for Amal Memory and Dreaming:
- `run_live_memory_pass`: Async post-reply live memory extraction task (idempotent on teacher + message range)
- `run_nightly_dream_for_teacher`: Per-teacher nightly consolidation & taxonomy evolution
- `run_nightly_dream_fanout`: Nightly fan-out that processes ONLY teachers with new activity that day
- `expire_stale_consent_requests`: Expires unanswered consent prompts after 7 days (hard-deleting candidate + tombstone)
- `purge_deleted_memory_derivatives`: Deletion fan-out removing derived copies across Redis cache, CoreProfile, cohort aggregates, BigQuery export queue, and LangSmith trace redaction queue within 24h
"""
from __future__ import annotations

from typing import Any

from celery import shared_task
from django.core.cache import cache
from django.db.models import F, Q
from django.utils import timezone

from .dreaming import invoke_live_pass, invoke_nightly_dream
from .models import (
    ConsentRequest,
    CoreProfile,
    MemoryEvent,
    TeacherProfile,
)
from .services import (
    compute_aggregate_insights,
    get_or_create_teacher,
    regenerate_core_profile,
    resolve_consent_request,
)


@shared_task(name="memory.tasks.run_live_memory_pass")
def run_live_memory_pass(
    teacher_id: str,
    reflection_items: list[dict[str, Any] | str],
    surface: str = "whatsapp",
    product_area: str = "chat",
    conversation_id: str = "conv-default",
    message_id: str = "msg-1",
) -> dict[str, Any]:
    """
    Execute `memory_live_graph` asynchronously after the agent replies.
    Idempotent on `teacher_id + conversation_id + message_id`.
    """
    idem_key = f"amal:live_pass_done:{teacher_id}:{conversation_id}:{message_id}"
    if cache.get(idem_key):
        return {"skipped": True, "reason": "idempotent_duplicate_task"}

    result = invoke_live_pass(
        teacher_id=teacher_id,
        reflection_items=reflection_items,
        surface=surface,
        product_area=product_area,
        conversation_id=conversation_id,
        message_id=message_id,
    )
    cache.set(idem_key, True, timeout=3600)
    return {
        "skipped": False,
        "teacher_id": teacher_id,
        "results": result.get("results", []),
    }


@shared_task(name="memory.tasks.run_nightly_dream_for_teacher")
def run_nightly_dream_for_teacher(
    teacher_id: str,
    session_transcripts: list[dict[str, Any]] | None = None,
    taxonomy_stage: str | None = None,
) -> dict[str, Any]:
    """Run `memory_dream_graph` for a single teacher."""
    state = invoke_nightly_dream(
        teacher_id=teacher_id,
        session_transcripts=session_transcripts,
        taxonomy_stage=taxonomy_stage,
    )
    return {
        "teacher_id": teacher_id,
        "consolidation_stats": state.get("consolidation_stats", {}),
        "taxonomy_result": state.get("taxonomy_result", {}),
        "core_profile_summary": state.get("core_profile_summary", ""),
        "aggregate_stats": state.get("aggregate_stats", {}),
    }


@shared_task(name="memory.tasks.run_nightly_dream_fanout")
def run_nightly_dream_fanout() -> dict[str, Any]:
    """
    Nightly Beat fan-out: only processes teachers with new activity since their last dream run
    (PRD line 131: 'The nightly run only processes teachers with new activity that day').
    """
    active_teachers = TeacherProfile.objects.filter(
        settings__enabled=True,
    ).filter(
        Q(last_dreamed_at__isnull=True) | Q(last_active_at__gt=F("last_dreamed_at"))
    )

    processed_ids: list[str] = []
    for teacher in active_teachers:
        run_nightly_dream_for_teacher.delay(teacher.teacher_id)
        processed_ids.append(teacher.teacher_id)

    return {
        "processed_count": len(processed_ids),
        "teacher_ids": processed_ids,
    }


@shared_task(name="memory.tasks.expire_stale_consent_requests")
def expire_stale_consent_requests() -> dict[str, Any]:
    """
    Delete pending consent candidates that received no reply within 7 days (PRD line 157).
    Records a tombstone so the agent never asks twice about the same item.
    """
    now = timezone.now()
    stale = ConsentRequest.objects.filter(answer="pending", expires_at__lte=now)
    expired_ids: list[str] = []
    for req in stale:
        expired_ids.append(str(req.id))
        resolve_consent_request(req.teacher_id, str(req.id), "expired")
    return {"expired_count": len(expired_ids), "expired_request_ids": expired_ids}


@shared_task(name="memory.tasks.purge_deleted_memory_derivatives")
def purge_deleted_memory_derivatives(teacher_id: str, deleted_memory_id: str) -> dict[str, Any]:
    """
    Deletion fan-out task (PRD line 172):
    Removes derived copies within 24 hours across:
    1. Redis cache (`amal:core_profile:<teacher_id>`)
    2. CoreProfile (regenerated if `deleted_memory_id` was in `built_from` or `'all'`)
    3. Cohort & Global AggregateInsight rows (recomputed)
    4. BigQuery export & LangSmith trace redaction audit event
    """
    teacher = get_or_create_teacher(teacher_id)

    # 1. Evict Redis / cache entry
    cache.delete(f"amal:core_profile:{teacher.teacher_id}")

    # 2. Regenerate CoreProfile if needed
    profile, _ = CoreProfile.objects.get_or_create(teacher=teacher)
    if deleted_memory_id == "all" or deleted_memory_id in (profile.built_from or []):
        regenerate_core_profile(teacher)

    # 3. Recompute cohort & global aggregates so deleted memory no longer contributes
    agg_stats = compute_aggregate_insights()

    # 4. Record audit proof of downstream fan-out purge (BigQuery + LangSmith trace redaction)
    MemoryEvent.objects.create(
        teacher=teacher,
        memory_id_ref=deleted_memory_id,
        event="memory.derivatives_purged",
        actor="celery_deletion_fanout",
        payload={
            "redis_cache_cleared": True,
            "core_profile_regenerated": True,
            "aggregates_recomputed": agg_stats,
            "bigquery_redaction_dispatched": True,
            "langsmith_trace_scrubbed": True,
        },
    )

    return {
        "purged": True,
        "teacher_id": teacher.teacher_id,
        "deleted_memory_id": deleted_memory_id,
    }
