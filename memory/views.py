"""
REST API views, Consent & Taxonomy endpoints, Admin Inspector, and Simple Categorical Web UI
for Amal Memory and Dreaming.
"""
from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .constants import CORE_CATEGORIES
from .llm import (
    extract_memories_with_llm,
    generate_chat_reply,
    is_llm_configured,
)
from .models import (
    AggregateInsight,
    ConsentRequest,
    MemoryCategory,
    MemoryCategoryLink,
    MemoryEvent,
    MemoryItem,
    MemoryNotification,
    MemoryTombstone,
    TaxonomyChangeset,
)
from .retrieval import (
    assemble_turn_context,
    handle_whatsapp_memory_command,
    hybrid_search,
)
from .services import (
    compute_undo_quality_metrics,
    delete_all_memories,
    delete_memory,
    edit_memory,
    get_or_create_teacher,
    regenerate_core_profile,
    resolve_consent_request,
    save_or_update_memory,
    seed_core_categories,
    set_memory_opt_out,
)
from .tasks import (
    run_live_memory_pass,
    run_nightly_dream_for_teacher,
)
from .taxonomy import (
    apply_taxonomy_changeset,
    teacher_manage_life_area,
    undo_taxonomy_changeset,
)


def _parse_body(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def _get_teacher_id(request: HttpRequest, body: dict[str, Any] | None = None) -> str:
    if body and body.get("teacher_id"):
        return str(body["teacher_id"])
    return getattr(request, "teacher_id", None) or request.GET.get("teacher_id") or "teacher-wambui-ke"


def _extract_short_teacher_name(teacher) -> str:
    """Extract a clean first/short name for category summaries (e.g. 'Wambui' or 'Baran')."""
    raw = (teacher.display_name or "").strip()
    if raw:
        # Remove parenthetical suffix like '(Kisumu Primary)' and titles like 'Mwalimu'
        cleaned = raw.split("(")[0].strip()
        for prefix in ("Mwalimu ", "Teacher ", "Mr. ", "Mr ", "Ms. ", "Ms ", "Mrs. ", "Mrs "):
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix):].strip()
        if cleaned:
            return cleaned.split()[0]
    tid = (teacher.teacher_id or "Teacher").replace("teacher-", "").replace("-ke", "").replace("-tz", "")
    parts = [p for p in tid.replace("_", "-").split("-") if p]
    return parts[0].capitalize() if parts else "Teacher"


def _build_category_summary(slug: str, label_en: str, short_name: str, is_life_area: bool = False) -> str:
    """Build a concise one-line category summary personalized with the teacher's name."""
    templates = {
        "profile": f"School, county, role, and professional background {short_name} has shared",
        "teaching_context": f"Grades, subjects, curriculum, and class sizes {short_name} teaches",
        "classroom": f"Classroom setup, available resources, and learner profile {short_name} works with",
        "practice": f"Reusable teaching strategies, skills, and classroom practices {short_name} has built and tried",
        "learning_journey": f"AI training modules, certifications, and skills {short_name} has completed",
        "ongoing_work": f"Reusable AI tooling, skills, lesson plans, and active projects {short_name} has built",
        "preferences": f"Language, response format, and tone preferences {short_name} uses",
        "people": f"Colleagues, mentors, and school contacts {short_name} collaborates with",
        "wellbeing": f"Workload, schedule constraints, and wellbeing notes {short_name} has shared",
        "named_learners": f"Individual learner notes and accommodations {short_name} tracks",
    }
    if slug in templates and not is_life_area:
        return templates[slug]
    lower_label = label_en.lower()
    if "ai" in lower_label or "tool" in lower_label or "skill" in lower_label:
        return f"Reusable AI tooling, skills, and prompt work {short_name} has built"
    if "master" in lower_label or "degree" in lower_label or "university" in lower_label:
        return f"Postgraduate coursework, thesis research, and university studies {short_name} is pursuing"
    return f"Reusable {lower_label} work, projects, and notes {short_name} has built"


def _format_last_updated(dt) -> str:
    """Format a timestamp as 'Sep 12, 2026' matching the memory card design."""
    if not dt:
        dt = timezone.now()
    return f"{dt.strftime('%b')} {dt.day}, {dt.year}"


def build_categorical_state(teacher_id: str) -> dict[str, Any]:
    """
    Assemble the complete categorical representation of a teacher's memory state:
    - Core Profile summary & metadata
    - All 10 Protected Core Categories (with subcategories, summary, last_updated, and active memories)
    - Dynamic Life Areas (active and archived)
    - Pending Consent queue (`pending_consent` items + ConsentRequest IDs)
    - Web Notifications (realtime banner, since-last-visit cards, taxonomy cards)
    - Superseded history & tombstone count
    - Settings & quality metrics
    """
    teacher = get_or_create_teacher(teacher_id)
    short_name = _extract_short_teacher_name(teacher)
    core_map = seed_core_categories()
    profile = getattr(teacher, "core_profile", None) or regenerate_core_profile(teacher)
    settings_obj = teacher.settings

    active_links = (
        MemoryCategoryLink.objects.filter(
            memory__teacher=teacher,
            memory__status="active",
            valid_to__isnull=True,
        )
        .select_related("memory", "category", "subcategory")
        .prefetch_related("memory__evidence")
        .order_by("-memory__recorded_at")
    )

    links_by_cat: dict[str, list[dict[str, Any]]] = {}
    latest_dt_by_cat: dict[str, Any] = {}
    for link in active_links:
        mem = link.memory
        ev = mem.evidence.first()
        cat_key = str(link.category_id)
        if mem.recorded_at and (cat_key not in latest_dt_by_cat or mem.recorded_at > latest_dt_by_cat[cat_key]):
            latest_dt_by_cat[cat_key] = mem.recorded_at
        links_by_cat.setdefault(cat_key, []).append(
            {
                "id": str(mem.id),
                "statement": mem.statement,
                "slot": mem.slot,
                "lang": mem.lang,
                "source": mem.source,
                "sensitivity": mem.sensitivity,
                "confidence": round(mem.confidence, 2),
                "salience": round(mem.salience, 2),
                "subcategory_id": str(link.subcategory_id) if link.subcategory_id else None,
                "subcategory_slug": link.subcategory.slug if link.subcategory else "general",
                "subcategory_label_en": link.subcategory.label_en if link.subcategory else "General",
                "subcategory_label_sw": link.subcategory.label_sw if link.subcategory else "Jumla",
                "surface": ev.surface if ev else "web",
                "product_area": ev.product_area if ev else "chat",
                "conversation_id": ev.conversation_id if ev else "",
                "created_by": mem.created_by,
                "valid_from": mem.valid_from.isoformat() if mem.valid_from else None,
                "recorded_at": mem.recorded_at.isoformat() if mem.recorded_at else None,
                "last_updated_display": _format_last_updated(mem.recorded_at),
            }
        )

    # 1. Protected Core Categories (all 10 always represented)
    core_categories_out: list[dict[str, Any]] = []
    for cat_seed in CORE_CATEGORIES:
        cat_obj = core_map[cat_seed["slug"]]
        subcats = list(
            MemoryCategory.objects.filter(parent=cat_obj, status="active")
            .order_by("created_at")
            .values("id", "slug", "label_en", "label_sw")
        )
        for s in subcats:
            s["id"] = str(s["id"])
        cat_id_str = str(cat_obj.id)
        cat_memories = links_by_cat.get(cat_id_str, [])
        cat_last_dt = latest_dt_by_cat.get(cat_id_str) or cat_obj.last_memory_at or cat_obj.created_at
        core_categories_out.append(
            {
                "id": cat_id_str,
                "slug": cat_obj.slug,
                "label_en": cat_obj.label_en,
                "label_sw": cat_obj.label_sw,
                "description": cat_seed["description"],
                "summary": _build_category_summary(cat_obj.slug, cat_obj.label_en, short_name, is_life_area=False),
                "last_updated": _format_last_updated(cat_last_dt),
                "sensitivity": cat_obj.sensitivity,
                "is_protected": True,
                "frozen_until": cat_obj.frozen_until.isoformat() if cat_obj.frozen_until else None,
                "subcategories": subcats,
                "memories": cat_memories,
                "memory_count": len(cat_memories),
            }
        )

    # 2. Dynamic Life Areas for this teacher
    life_area_objs = MemoryCategory.objects.filter(
        teacher=teacher,
        kind="life_area",
    ).exclude(status="merged").order_by("-status", "created_at")

    life_areas_out: list[dict[str, Any]] = []
    for la in life_area_objs:
        subcats = list(
            MemoryCategory.objects.filter(parent=la, status="active")
            .order_by("created_at")
            .values("id", "slug", "label_en", "label_sw")
        )
        for s in subcats:
            s["id"] = str(s["id"])
        la_id_str = str(la.id)
        la_memories = links_by_cat.get(la_id_str, [])
        la_last_dt = latest_dt_by_cat.get(la_id_str) or la.last_memory_at or la.created_at
        life_areas_out.append(
            {
                "id": la_id_str,
                "slug": la.slug,
                "label_en": la.label_en,
                "label_sw": la.label_sw,
                "summary": _build_category_summary(la.slug, la.label_en, short_name, is_life_area=True),
                "last_updated": _format_last_updated(la_last_dt),
                "status": la.status,
                "created_by": la.created_by,
                "frozen_until": la.frozen_until.isoformat() if la.frozen_until else None,
                "subcategories": subcats,
                "memories": la_memories,
                "memory_count": len(la_memories),
            }
        )

    # 3. Pending Consent queue (never in active retrieval)
    pending_consents_qs = (
        ConsentRequest.objects.filter(teacher=teacher, answer="pending")
        .select_related("memory")
        .order_by("-asked_at")
    )
    pending_consents_out: list[dict[str, Any]] = []
    for req in pending_consents_qs:
        if not req.memory:
            continue
        lnk = MemoryCategoryLink.objects.filter(memory=req.memory).select_related("category", "subcategory").first()
        pending_consents_out.append(
            {
                "consent_id": str(req.id),
                "memory_id": str(req.memory.id),
                "statement": req.memory.statement,
                "prompt_text": req.prompt_text,
                "slot": req.slot,
                "category_slug": lnk.category.slug if lnk else "people",
                "category_label": lnk.category.label_en if lnk else "People",
                "subcategory_label": lnk.subcategory.label_en if (lnk and lnk.subcategory) else "",
                "channel": req.channel,
                "asked_at": req.asked_at.isoformat(),
                "expires_at": req.expires_at.isoformat(),
            }
        )

    # 4. Notifications (banners, external WhatsApp/dreaming saves, taxonomy cards)
    notifs_qs = (
        MemoryNotification.objects.filter(teacher=teacher)
        .select_related("memory", "changeset")
        .order_by("-created_at")[:30]
    )
    notifications_out: list[dict[str, Any]] = []
    for n in notifs_qs:
        notifications_out.append(
            {
                "id": str(n.id),
                "kind": n.kind,
                "title": n.title,
                "body": n.body,
                "diff_before": n.diff_before,
                "diff_after": n.diff_after,
                "category_slug": n.category_slug,
                "origin_surface": n.origin_surface,
                "grouped_count": n.grouped_count,
                "memory_id": str(n.memory_id) if n.memory_id else None,
                "changeset_id": str(n.changeset_id) if n.changeset_id else None,
                "changeset_status": n.changeset.status if n.changeset else None,
                "action": n.action,
                "seen_at": n.seen_at.isoformat() if n.seen_at else None,
                "created_at": n.created_at.isoformat(),
            }
        )

    # 5. Superseded bi-temporal history
    superseded_qs = MemoryItem.objects.filter(teacher=teacher, status="superseded").order_by("-retired_at")[:15]
    superseded_out = [
        {
            "id": str(m.id),
            "statement": m.statement,
            "slot": m.slot,
            "valid_from": m.valid_from.isoformat() if m.valid_from else None,
            "valid_to": m.valid_to.isoformat() if m.valid_to else None,
            "retired_at": m.retired_at.isoformat() if m.retired_at else None,
            "superseded_by_id": str(m.superseded_by_id) if m.superseded_by_id else None,
        }
        for m in superseded_qs
    ]

    # 6. Taxonomy changesets
    changesets_qs = TaxonomyChangeset.objects.filter(teacher=teacher).prefetch_related("operations")[:10]
    changesets_out = [
        {
            "id": str(cs.id),
            "status": cs.status,
            "summary_en": cs.summary_en,
            "summary_sw": cs.summary_sw,
            "operations": [
                {
                    "op_type": op.op_type,
                    "before_state": op.before_state,
                    "after_state": op.after_state,
                }
                for op in cs.operations.all()
            ],
            "created_at": cs.created_at.isoformat(),
        }
        for cs in changesets_qs
    ]

    return {
        "teacher": {
            "teacher_id": teacher.teacher_id,
            "display_name": teacher.display_name,
            "country": teacher.country,
            "cohort_key": teacher.cohort_key,
            "curriculum": teacher.curriculum,
            "preferred_lang": teacher.preferred_lang,
            "last_active_at": teacher.last_active_at.isoformat() if teacher.last_active_at else None,
            "last_dreamed_at": teacher.last_dreamed_at.isoformat() if teacher.last_dreamed_at else None,
        },
        "settings": {
            "enabled": settings_obj.enabled,
            "share_aggregate": settings_obj.share_aggregate,
            "sensitive_mode": settings_obj.sensitive_mode,
            "banner_mode": settings_obj.banner_mode,
        },
        "core_profile": {
            "summary": profile.summary,
            "version": profile.version,
            "built_from_count": len(profile.built_from or []),
        },
        "core_categories": core_categories_out,
        "life_areas": life_areas_out,
        "pending_consents": pending_consents_out,
        "notifications": notifications_out,
        "unread_notification_count": sum(1 for n in notifications_out if n["action"] == "pending" and not n["seen_at"]),
        "superseded_history": superseded_out,
        "taxonomy_changesets": changesets_out,
        "tombstone_count": MemoryTombstone.objects.filter(teacher=teacher).count(),
        "quality_metrics": compute_undo_quality_metrics(),
        "llm_status": {
            "chat_model": getattr(settings, "AMAL_CHAT_MODEL", "claude-3-5-haiku-latest"),
            "extraction_model": getattr(settings, "AMAL_EXTRACTION_MODEL", "claude-3-5-haiku-latest"),
            "api_key_configured": is_llm_configured(),
            "db_engine": settings.DATABASES["default"]["ENGINE"].split(".")[-1],
        },
    }


def dashboard_view(request: HttpRequest) -> HttpResponse:
    """Render the user-facing Amal Web Chat + Categorical Memory interface."""
    teacher_id = _get_teacher_id(request)
    get_or_create_teacher(teacher_id)
    return render(request, "memory/dashboard.html", {"teacher_id": teacher_id})


@csrf_exempt
@require_http_methods(["POST"])
def api_chat(request: HttpRequest) -> JsonResponse:
    """
    Conversational endpoint for chatting with the Amal Assistant (Claude Haiku):
    1. Handles explicit memory commands ('What do you remember about me?', 'Forget...', 'YES'/'NO' consent replies)
    2. Assembles per-turn memory context (`CoreProfile` + 3-signal RRF hybrid search)
    3. Generates assistant reply using Claude Haiku (`AMAL_CHAT_MODEL`)
    4. Extracts candidate memories from the teacher's message using the LLM extraction model (`AMAL_EXTRACTION_MODEL`)
       and persists them via `run_live_memory_pass`.
    """
    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    user_message = (body.get("message") or "").strip()
    if not user_message:
        return JsonResponse({"error": "Message is required"}, status=400)

    surface = body.get("surface", "web")
    product_area = body.get("product_area", "chat")
    conversation_id = body.get("conversation_id", "conv-web-chat")
    message_id = body.get("message_id", f"msg-{int(timezone.now().timestamp() * 1000)}")
    chat_history = body.get("history") or []
    api_key_override = (body.get("api_key") or "").strip() or None

    teacher = get_or_create_teacher(teacher_id)

    # 1. Check if the teacher issued a synchronous memory control command or consent reply
    cmd_res = handle_whatsapp_memory_command(teacher_id, user_message)
    if cmd_res.get("handled"):
        return JsonResponse(
            {
                "reply": cmd_res.get("reply", ""),
                "command_handled": cmd_res.get("command"),
                "chat_model": "amal-memory-tool",
                "extraction_model": "amal-memory-tool",
                "live_llm": is_llm_configured(api_key_override),
                "turn_context": {
                    "retrieved_memories": [],
                    "skipped_retrieval": True,
                    "latency_ms": 0.0,
                },
                "extracted_candidates": [],
                "live_pass_results": [cmd_res.get("result")] if cmd_res.get("result") else [],
                "state": build_categorical_state(teacher_id),
            }
        )

    # 2. Assemble turn context (CoreProfile + 3-signal RRF hybrid search)
    turn_context = assemble_turn_context(
        teacher_id=teacher_id,
        user_message=user_message,
        surface=surface,
        product_area=product_area,
    )

    # 3. Call Claude Haiku to generate the assistant's reply with injected memory context
    chat_out = generate_chat_reply(
        user_message=user_message,
        turn_context=turn_context,
        chat_history=chat_history,
        teacher_name=teacher.display_name or teacher.teacher_id,
        api_key_override=api_key_override,
    )

    # 4. Run LLM Memory Extraction (`extract_memories_with_llm`) + Live Pass persistence
    active_life_areas = list(
        MemoryCategory.objects.filter(
            teacher=teacher,
            kind="life_area",
            status="active",
        ).values("slug", "label_en")
    )
    extracted_candidates, ext_model_used, ext_live_llm = extract_memories_with_llm(
        conversation_text=user_message,
        core_profile_summary=turn_context.get("core_profile", ""),
        active_life_areas=active_life_areas,
        api_key_override=api_key_override,
    )

    live_pass_results: list[dict[str, Any]] = []
    if extracted_candidates:
        task_out = run_live_memory_pass.delay(
            teacher_id=teacher_id,
            reflection_items=extracted_candidates,
            surface=surface,
            product_area=product_area,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        res_data = task_out.get() if hasattr(task_out, "get") else task_out
        live_pass_results = res_data.get("results", [])

    return JsonResponse(
        {
            "reply": chat_out["reply"],
            "chat_model": chat_out["model"],
            "extraction_model": ext_model_used,
            "live_llm": bool(chat_out["live_llm"] or ext_live_llm),
            "llm_error": chat_out.get("error"),
            "turn_context": turn_context,
            "extracted_candidates": extracted_candidates,
            "live_pass_results": live_pass_results,
            "state": build_categorical_state(teacher_id),
        }
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_memories(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        teacher_id = _get_teacher_id(request)
        return JsonResponse(build_categorical_state(teacher_id))

    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    result = save_or_update_memory(
        teacher_id=teacher_id,
        statement=body.get("statement", ""),
        category_slug=body.get("category_slug"),
        subcategory_slug=body.get("subcategory_slug"),
        source=body.get("source", "stated"),
        surface=body.get("surface", "web"),
        product_area=body.get("product_area", "chat"),
        conversation_id=body.get("conversation_id", "conv-web"),
        created_by=body.get("created_by", "teacher"),
        explicit_consent_granted=bool(body.get("explicit_consent_granted", False)),
    )
    return JsonResponse({"result": result, "state": build_categorical_state(teacher_id)})


@csrf_exempt
@require_http_methods(["PATCH", "PUT", "DELETE"])
def api_memory_detail(request: HttpRequest, memory_id: str) -> JsonResponse:
    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    if request.method in ("PATCH", "PUT"):
        new_statement = body.get("statement", "")
        result = edit_memory(teacher_id=teacher_id, memory_id=memory_id, new_statement=new_statement, actor="teacher")
        return JsonResponse({"result": result, "state": build_categorical_state(teacher_id)})

    is_undo = request.GET.get("undo", "false").lower() == "true" or bool(body.get("undo"))
    result = delete_memory(
        teacher_id=teacher_id,
        memory_id=memory_id,
        actor="teacher",
        record_tombstone=True,
        is_undo=is_undo,
    )
    return JsonResponse({"result": result, "state": build_categorical_state(teacher_id)})


@csrf_exempt
@require_http_methods(["POST"])
def api_delete_all(request: HttpRequest) -> JsonResponse:
    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    result = delete_all_memories(teacher_id=teacher_id, actor="teacher")
    return JsonResponse({"result": result, "state": build_categorical_state(teacher_id)})


@require_http_methods(["GET"])
def api_export_memories(request: HttpRequest) -> HttpResponse:
    teacher_id = _get_teacher_id(request)
    state = build_categorical_state(teacher_id)
    payload = json.dumps(state, indent=2)
    response = HttpResponse(payload, content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="amal_memories_{teacher_id}.json"'
    return response


@require_http_methods(["GET"])
def api_download_repo_zip(request: HttpRequest) -> HttpResponse:
    """Download the tracked git repository as a .zip archive."""
    import subprocess
    proc = subprocess.run(
        ["git", "archive", "--format=zip", "HEAD"],
        cwd=str(settings.BASE_DIR),
        capture_output=True,
        check=True,
    )
    response = HttpResponse(proc.stdout, content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="amal_agent_memory.zip"'
    return response


@require_http_methods(["GET"])
def api_download_git_bundle(request: HttpRequest) -> HttpResponse:
    """Download the complete git repository history as a git bundle file."""
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".bundle") as tmp:
        subprocess.run(
            ["git", "bundle", "create", tmp.name, "--all"],
            cwd=str(settings.BASE_DIR),
            check=True,
        )
        tmp.seek(0)
        data = tmp.read()
    response = HttpResponse(data, content_type="application/octet-stream")
    response["Content-Disposition"] = 'attachment; filename="amal_agent_memory.bundle"'
    return response


@csrf_exempt
@require_http_methods(["POST"])
def api_resolve_consent(request: HttpRequest, consent_id: str) -> JsonResponse:
    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    answer = body.get("answer", "no")
    result = resolve_consent_request(teacher_id=teacher_id, consent_request_id=consent_id, answer=answer)
    return JsonResponse({"result": result, "state": build_categorical_state(teacher_id)})


@csrf_exempt
@require_http_methods(["POST"])
def api_notification_action(request: HttpRequest, notification_id: str) -> JsonResponse:
    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    action = body.get("action", "kept")
    teacher = get_or_create_teacher(teacher_id)
    notif = MemoryNotification.objects.filter(id=notification_id, teacher=teacher).first()
    if not notif:
        return JsonResponse({"ok": False, "reason": "not_found"}, status=404)

    now = timezone.now()
    if action in ("undo", "undone", "remove", "removed"):
        if notif.changeset_id:
            undo_taxonomy_changeset(teacher_id, str(notif.changeset_id))
        elif notif.memory_id:
            delete_memory(
                teacher_id=teacher_id,
                memory_id=str(notif.memory_id),
                actor="teacher",
                record_tombstone=True,
                is_undo=(action in ("undo", "undone")),
            )
        notif.action = "undone" if action in ("undo", "undone") else "removed"
        notif.seen_at = now
        notif.save(update_fields=["action", "seen_at"])
    else:
        notif.action = "kept"
        notif.seen_at = now
        notif.save(update_fields=["action", "seen_at"])

    return JsonResponse({"ok": True, "state": build_categorical_state(teacher_id)})


@csrf_exempt
@require_http_methods(["POST"])
def api_live_pass(request: HttpRequest) -> JsonResponse:
    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    surface = body.get("surface", "whatsapp")
    product_area = body.get("product_area", "chat")
    conversation_id = body.get("conversation_id", f"conv-{int(timezone.now().timestamp())}")
    message_id = body.get("message_id", f"msg-{int(timezone.now().timestamp() * 1000)}")

    raw_message = (body.get("message") or "").strip()
    if raw_message:
        cmd_res = handle_whatsapp_memory_command(teacher_id, raw_message)
        if cmd_res.get("handled"):
            return JsonResponse({"command_result": cmd_res, "state": build_categorical_state(teacher_id)})

    reflection_items = body.get("reflection_items") or ([raw_message] if raw_message else [])
    task_out = run_live_memory_pass.delay(
        teacher_id=teacher_id,
        reflection_items=reflection_items,
        surface=surface,
        product_area=product_area,
        conversation_id=conversation_id,
        message_id=message_id,
    )
    res_data = task_out.get() if hasattr(task_out, "get") else task_out
    return JsonResponse({"live_pass": res_data, "state": build_categorical_state(teacher_id)})


@csrf_exempt
@require_http_methods(["POST"])
def api_dream_run(request: HttpRequest) -> JsonResponse:
    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    transcripts = body.get("session_transcripts") or []
    taxonomy_stage = body.get("taxonomy_stage")
    task_out = run_nightly_dream_for_teacher.delay(
        teacher_id=teacher_id,
        session_transcripts=transcripts,
        taxonomy_stage=taxonomy_stage,
    )
    res_data = task_out.get() if hasattr(task_out, "get") else task_out
    return JsonResponse({"dream_run": res_data, "state": build_categorical_state(teacher_id)})


@csrf_exempt
@require_http_methods(["POST"])
def api_retrieve_context(request: HttpRequest) -> JsonResponse:
    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    query = body.get("query", "")
    surface = body.get("surface", "web")
    product_area = body.get("product_area", "chat")
    context = assemble_turn_context(
        teacher_id=teacher_id,
        user_message=query,
        surface=surface,
        product_area=product_area,
    )
    return JsonResponse({"context": context})


@csrf_exempt
@require_http_methods(["POST"])
def api_taxonomy_undo(request: HttpRequest, changeset_id: str) -> JsonResponse:
    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    result = undo_taxonomy_changeset(teacher_id=teacher_id, changeset_id=changeset_id)
    return JsonResponse({"result": result, "state": build_categorical_state(teacher_id)})


@csrf_exempt
@require_http_methods(["POST"])
def api_taxonomy_apply(request: HttpRequest, changeset_id: str) -> JsonResponse:
    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    result = apply_taxonomy_changeset(changeset_id=changeset_id)
    return JsonResponse({"result": result, "state": build_categorical_state(teacher_id)})


@csrf_exempt
@require_http_methods(["POST"])
def api_life_areas(request: HttpRequest) -> JsonResponse:
    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    result = teacher_manage_life_area(
        teacher_id=teacher_id,
        action=body.get("action", "create"),
        label_en=body.get("label_en", ""),
        label_sw=body.get("label_sw", ""),
        category_id=body.get("category_id"),
        target_category_id=body.get("target_category_id"),
    )
    return JsonResponse({"result": result, "state": build_categorical_state(teacher_id)})


@csrf_exempt
@require_http_methods(["POST"])
def api_settings(request: HttpRequest) -> JsonResponse:
    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    teacher = get_or_create_teacher(teacher_id)
    settings_obj = teacher.settings

    if "enabled" in body and bool(body["enabled"]) != settings_obj.enabled:
        set_memory_opt_out(teacher_id, enabled=bool(body["enabled"]))
        settings_obj.refresh_from_db()

    if "share_aggregate" in body:
        settings_obj.share_aggregate = bool(body["share_aggregate"])
    if "sensitive_mode" in body and body["sensitive_mode"] in ("always_ask", "never_remember"):
        settings_obj.sensitive_mode = body["sensitive_mode"]
    if "banner_mode" in body and body["banner_mode"] in ("realtime", "next_visit_summary"):
        settings_obj.banner_mode = body["banner_mode"]
    settings_obj.save()

    return JsonResponse({"state": build_categorical_state(teacher_id)})


@csrf_exempt
@require_http_methods(["POST", "DELETE"])
def api_clear_category(request: HttpRequest, category_id: str) -> JsonResponse:
    """
    Delete a dynamic life area or delete all active memories inside a protected core category.
    """
    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    teacher = get_or_create_teacher(teacher_id)
    cat = MemoryCategory.objects.filter(id=category_id).first()
    if not cat:
        return JsonResponse({"ok": False, "reason": "not_found"}, status=404)

    if cat.kind == "life_area" and cat.teacher_id == teacher.id:
        res = teacher_manage_life_area(
            teacher_id=teacher_id,
            action="delete",
            category_id=str(cat.id),
        )
        return JsonResponse({"result": res, "state": build_categorical_state(teacher_id)})

    # Protected core category: delete all active memories linked to this category for this teacher
    links = list(
        MemoryCategoryLink.objects.filter(
            memory__teacher=teacher,
            memory__status="active",
            category=cat,
            valid_to__isnull=True,
        ).select_related("memory")
    )
    deleted_ids = []
    for lnk in links:
        delete_memory(
            teacher_id=teacher_id,
            memory_id=str(lnk.memory_id),
            actor="teacher",
            record_tombstone=True,
        )
        deleted_ids.append(str(lnk.memory_id))
    return JsonResponse(
        {
            "result": {"deleted_count": len(deleted_ids), "deleted_ids": deleted_ids},
            "state": build_categorical_state(teacher_id),
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def api_seed_demo(request: HttpRequest) -> JsonResponse:
    """
    Seed realistic memories in the exact concise, verb-led bullet wording from image.png:
    - 'AI Tooling' Life Area with the 4 AI tooling bullets from the reference screenshot
    - Protected Core Categories for classroom & teaching context
    - A pending sensitive consent item ('Co-plans Science lessons with colleague Wanjiru')
    - 5 Master's degree memories across 2 conversations to demonstrate Nightly Dreaming taxonomy evolution.
    """
    body = _parse_body(request)
    teacher_id = _get_teacher_id(request, body)
    teacher = get_or_create_teacher(
        teacher_id=teacher_id,
        display_name="Mwalimu Wambui (Kisumu Primary)",
        country="KE",
        cohort_key="kisumu-cohort-1",
        curriculum="CBC",
        preferred_lang="en",
    )

    # Ensure the 'AI Tooling' Life Area exists so the exact card from image.png is immediately visible
    teacher_manage_life_area(
        teacher_id=teacher.teacher_id,
        action="create",
        label_en="AI Tooling",
        label_sw="Zana za AI",
    )

    sample_memories = [
        # Exact 'AI Tooling' bullets from image.png
        ("Built a gradual-release-instructor skill using the skill-creator system", "ai_tooling", "skills_built", "stated", "web", "conv-ai-1"),
        ("Built a Socratic tutor skill using the skill-creator system", "ai_tooling", "skills_built", "stated", "web", "conv-ai-1"),
        ("Built an Anki card creator skill", "ai_tooling", "anki_skill", "stated", "web", "conv-ai-1"),
        ("Does prompt optimization for WhatsApp agents", "ai_tooling", "prompt_optimization", "stated", "web", "conv-ai-2"),
        # Core classroom & teaching categories in the same concise verb-led wording
        ("Teaches at a public primary school in Kisumu County", "profile", "school", "stated", "whatsapp", "conv-1"),
        ("Teaches Grade 6 Mathematics and Science under CBC", "teaching_context", "subjects", "stated", "whatsapp", "conv-1"),
        ("Has around 60 learners per class", "teaching_context", "class_size", "stated", "whatsapp", "conv-1"),
        ("Lacks a classroom projector; uses chalkboard and manila charts", "classroom", "resources", "stated", "web", "conv-2"),
        ("Ran group work in Science that went well; wants to try peer assessment", "practice", "what_worked", "stated", "web", "conv-2"),
        ("Completed Foundations of AI Level 1, Module 3", "learning_journey", "modules", "observed", "web", "conv-2"),
        ("Preparing Term 2 scheme of work for Grade 6 Maths", "ongoing_work", "active_projects", "stated", "web", "conv-2"),
        ("Prefers Kiswahili and English mix, short answers, and bullet-point plans", "preferences", "format", "stated", "whatsapp", "conv-1"),
        # Sensitive memory -> goes to pending_consent queue
        ("Co-plans with her colleague Wanjiru", "people", "colleagues", "stated", "whatsapp", "conv-3"),
        # 5 memories across 2 conversations about Master's degree -> triggers New Life Area when Nightly Dreaming runs
        ("Enrolled in a Master's degree in Education Leadership at university", "profile", "identity", "stated", "whatsapp", "conv-m1"),
        ("Writing postgraduate master's thesis proposal on rural school leadership", "profile", "identity", "stated", "whatsapp", "conv-m1"),
        ("Taking university semester coursework in research methods for Master's degree", "profile", "identity", "stated", "whatsapp", "conv-m1"),
        ("Meeting university thesis supervisor on Friday for Master's dissertation", "profile", "identity", "stated", "web", "conv-m2"),
        ("Collecting postgraduate research survey data for Master's degree thesis", "profile", "identity", "stated", "web", "conv-m2"),
    ]

    for idx, (stmt, cat, sub, src, surf, conv_id) in enumerate(sample_memories):
        save_or_update_memory(
            teacher_id=teacher.teacher_id,
            statement=stmt,
            category_slug=cat,
            subcategory_slug=sub,
            source=src,
            surface=surf,
            conversation_id=conv_id,
            message_id=f"seed-msg-{idx}",
            created_by="live_pass",
        )

    return JsonResponse({"seeded": True, "state": build_categorical_state(teacher_id)})


@require_http_methods(["GET"])
def api_admin_inspect(request: HttpRequest) -> JsonResponse:
    """
    Admin memory inspector (engine.amal.education):
    Support staff access to a teacher's memories is logged and requires an explicit reason
    (PRD lines 293 & 324).
    """
    teacher_id = _get_teacher_id(request)
    reason = (request.GET.get("reason") or "").strip()
    admin_actor = (request.GET.get("admin_user") or "support@amal.education").strip()
    if not reason:
        return JsonResponse(
            {"error": "Support access to teacher memories requires an explicit audit 'reason' parameter."},
            status=400,
        )

    teacher = get_or_create_teacher(teacher_id)
    MemoryEvent.objects.create(
        teacher=teacher,
        event="admin.inspected",
        actor=admin_actor,
        payload={"reason": reason},
    )

    state = build_categorical_state(teacher_id)
    audit_events = list(
        MemoryEvent.objects.filter(teacher=teacher)
        .values("id", "event", "actor", "memory_id_ref", "payload", "created_at")[:25]
    )
    for ev in audit_events:
        ev["id"] = str(ev["id"])
        ev["created_at"] = ev["created_at"].isoformat()

    insights = list(
        AggregateInsight.objects.all().values("scope", "scope_key", "statement", "n_teachers")[:20]
    )
    return JsonResponse(
        {
            "inspected_teacher_id": teacher_id,
            "audit_logged": True,
            "reason": reason,
            "state": state,
            "audit_events": audit_events,
            "aggregate_insights": insights,
        }
    )
