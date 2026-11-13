"""
Core transactional services for Amal Memory:
seeding, saving, superseding, consent gating, teacher editing, hard deletion with HMAC tombstones,
core profile generation, and privacy-preserving cohort/global aggregation.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .constants import (
    BANNER_GROUP_WINDOW_SECONDS,
    COHORT_MIN_TEACHERS,
    CONSENT_CATEGORY_SLUGS,
    CORE_CATEGORIES,
    CORE_PROFILE_CATEGORY_SLUGS,
    CORE_PROFILE_MAX_TOKENS,
    GLOBAL_MIN_TEACHERS,
)
from .embeddings import (
    compute_centroid,
    cosine_similarity,
    embed_text,
    simple_tokenize,
    trigram_similarity,
)
from .guardrails import (
    check_guardrails,
    detect_language,
    infer_category_and_slot,
    pseudonymize_learner_name,
)
from .models import (
    AggregateInsight,
    ConsentRequest,
    CoreProfile,
    MemoryCategory,
    MemoryCategoryLink,
    MemoryEvent,
    MemoryEvidence,
    MemoryItem,
    MemoryNotification,
    MemorySettings,
    MemoryTombstone,
    TeacherProfile,
)

SINGLETON_SLOTS = {
    "teaching_context.class_size",
    "teaching_context.grade_level",
    "preferences.language",
    "preferences.length",
    "preferences.format",
    "profile.school",
}


FIRST_PERSON_TO_BULLET_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(?:the\s+teacher|teacher|the\s+user|user)\s+", re.I), ""),
    (re.compile(r"^i(?:'ve|\s+have)?\s+built\b", re.I), "Built"),
    (re.compile(r"^i(?:'ve|\s+have)?\s+created\b", re.I), "Created"),
    (re.compile(r"^i(?:'ve|\s+have)?\s+developed\b", re.I), "Developed"),
    (re.compile(r"^i(?:'ve|\s+have)?\s+completed\b", re.I), "Completed"),
    (re.compile(r"^i(?:'ve|\s+have)?\s+tried\b", re.I), "Tried"),
    (re.compile(r"^i(?:'ve|\s+have)?\s+enrolled\b", re.I), "Enrolled"),
    (re.compile(r"^i\s+am\s+enrolled\b", re.I), "Enrolled"),
    (re.compile(r"^i\s+do\b", re.I), "Does"),
    (re.compile(r"^i(?:\s+am\s+working|\s+work)\s+on\b", re.I), "Works on"),
    (re.compile(r"^i(?:\s+am\s+teaching|\s+teach)\b", re.I), "Teaches"),
    (re.compile(r"^i(?:\s+am\s+using|\s+use)\b", re.I), "Uses"),
    (re.compile(r"^i(?:\s+am\s+building|\s+build)\b", re.I), "Builds"),
    (re.compile(r"^i(?:\s+am\s+preparing|\s+prepare)\b", re.I), "Preparing"),
    (re.compile(r"^i(?:\s+am\s+writing|\s+write)\b", re.I), "Writing"),
    (re.compile(r"^i(?:\s+am\s+taking|\s+take)\b", re.I), "Taking"),
    (re.compile(r"^i(?:\s+am\s+collecting|\s+collect)\b", re.I), "Collecting"),
    (re.compile(r"^i(?:\s+am\s+meeting|\s+meet)\b", re.I), "Meeting"),
    (re.compile(r"^i(?:\s+am\s+coaching|\s+coach)\b", re.I), "Coaches"),
    (re.compile(r"^i\s+prefer\b", re.I), "Prefers"),
    (re.compile(r"^i\s+want\b", re.I), "Wants"),
    (re.compile(r"^i\s+need\b", re.I), "Needs"),
    (re.compile(r"^i(?:\s+am\s+feeling|\s+feel)\b", re.I), "Feels"),
    (re.compile(r"^i\s+co-?plan\b", re.I), "Co-plans"),
    (re.compile(r"^(?:we|i|my\s+class(?:room)?)\s+(?:have|has)\s+no\b", re.I), "No"),
    (re.compile(r"^(?:we|i|my\s+class(?:room)?)\s+(?:have|has)\b", re.I), "Has"),
    (re.compile(r"^i(?:'m|\s+am)\s+a\b", re.I), "Is a"),
]


def format_memory_bullet_wording(statement: str) -> str:
    """
    Format a memory statement into concise, subjectless verb-led bullet wording
    (e.g., 'Built a gradual-release-instructor skill using the skill-creator system',
    'Does prompt optimization for WhatsApp agents', 'Teaches Grade 6 Mathematics and Science').
    """
    if not statement:
        return ""
    text = statement.strip()
    text = re.sub(r"^[\s•\-\*]+", "", text).strip()
    text = text.rstrip(".")
    for pattern, replacement in FIRST_PERSON_TO_BULLET_RULES:
        new_text, count = pattern.subn(replacement, text, count=1)
        if count > 0:
            text = new_text.strip()
            break
    if text:
        text = text[0].upper() + text[1:]
    return text


def normalize_statement(statement: str) -> str:
    """Normalize statement text for deterministic HMAC tombstone hashing."""
    formatted = format_memory_bullet_wording(statement)
    cleaned = re.sub(r"[^\w\s]", "", formatted.lower().strip())
    return re.sub(r"\s+", " ", cleaned)


def compute_statement_hmac(teacher_id: str, statement: str, slot: str) -> str:
    """
    Compute keyed HMAC-SHA256 of normalized statement + category slot.
    Tombstones store only this HMAC and slot—never raw text or embeddings.
    """
    secret = getattr(settings, "AMAL_MEMORY_TOMBSTONE_SECRET", "amal-tombstone-hmac-key-2026")
    norm = normalize_statement(statement)
    message = f"{teacher_id}:{slot}:{norm}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def seed_core_categories() -> dict[str, MemoryCategory]:
    """
    Idempotently seed the 10 protected core categories and their initial subcategories.
    Returns a map of slug -> top-level MemoryCategory.
    """
    seeded: dict[str, MemoryCategory] = {}
    for cat_def in CORE_CATEGORIES:
        cat_obj, created = MemoryCategory.objects.get_or_create(
            teacher=None,
            slug=cat_def["slug"],
            kind="core",
            defaults={
                "label_en": cat_def["label_en"],
                "label_sw": cat_def["label_sw"],
                "sensitivity": cat_def["sensitivity"],
                "is_protected": True,
                "status": "active",
                "created_by": "system",
                "centroid": embed_text(f"{cat_def['label_en']} {cat_def['description']} {cat_def['label_sw']}"),
            },
        )
        if not cat_obj.centroid:
            cat_obj.centroid = embed_text(f"{cat_def['label_en']} {cat_def['description']} {cat_def['label_sw']}")
            cat_obj.save(update_fields=["centroid", "path"])
        seeded[cat_def["slug"]] = cat_obj

        for sub_def in cat_def["subcategories"]:
            sub_obj, _ = MemoryCategory.objects.get_or_create(
                teacher=None,
                parent=cat_obj,
                slug=sub_def["slug"],
                kind="sub",
                defaults={
                    "label_en": sub_def["label_en"],
                    "label_sw": sub_def["label_sw"],
                    "sensitivity": cat_def["sensitivity"],
                    "is_protected": False,
                    "status": "active",
                    "created_by": "system",
                    "centroid": embed_text(f"{cat_def['label_en']} {sub_def['label_en']} {sub_def['label_sw']}"),
                },
            )
            if not sub_obj.centroid:
                sub_obj.centroid = embed_text(f"{cat_def['label_en']} {sub_def['label_en']} {sub_def['label_sw']}")
                sub_obj.save(update_fields=["centroid", "path"])
    return seeded


def get_or_create_teacher(
    teacher_id: str,
    display_name: str = "",
    country: str = "KE",
    cohort_key: str = "kisumu-cohort-1",
    curriculum: str = "CBC",
    preferred_lang: str = "en",
) -> TeacherProfile:
    """Ensure TeacherProfile, MemorySettings, CoreProfile, and global core categories exist."""
    seed_core_categories()
    teacher, _ = TeacherProfile.objects.get_or_create(
        teacher_id=teacher_id,
        defaults={
            "display_name": display_name or f"Mwalimu {teacher_id.split('-')[1].capitalize() if '-' in teacher_id else teacher_id}",
            "country": country,
            "cohort_key": cohort_key,
            "curriculum": curriculum,
            "preferred_lang": preferred_lang,
        },
    )
    MemorySettings.objects.get_or_create(teacher=teacher)
    CoreProfile.objects.get_or_create(teacher=teacher)
    return teacher


def resolve_category_and_subcategory(
    teacher: TeacherProfile,
    category_slug: str,
    subcategory_slug: str,
) -> tuple[MemoryCategory, MemoryCategory | None]:
    """
    Resolve a top-level category (core or teacher life_area) and optional subcategory.
    Automatically reactivates an archived life area when the topic returns (PRD line 105).
    """
    seed_core_categories()
    top_cat = (
        MemoryCategory.objects.filter(teacher=teacher, slug=category_slug, kind="life_area")
        .exclude(status="merged")
        .first()
        or MemoryCategory.objects.filter(teacher__isnull=True, slug=category_slug, kind="core").first()
        or MemoryCategory.objects.filter(teacher__isnull=True, slug="profile", kind="core").first()
    )
    assert top_cat is not None

    # Auto-reactivate archived life area when a new memory in the topic arrives
    if top_cat.kind == "life_area" and top_cat.status == "archived":
        top_cat.status = "active"
        top_cat.last_memory_at = timezone.now()
        top_cat.save(update_fields=["status", "last_memory_at"])

    sub_cat = None
    if subcategory_slug:
        sub_cat = (
            MemoryCategory.objects.filter(parent=top_cat, slug=subcategory_slug, status="active")
            .filter(models_q_teacher_or_global(teacher))
            .first()
        )
        if not sub_cat:
            sub_cat = MemoryCategory.objects.create(
                teacher=teacher if top_cat.teacher_id else None,
                parent=top_cat,
                slug=subcategory_slug,
                label_en=subcategory_slug.replace("_", " ").capitalize(),
                label_sw=subcategory_slug.replace("_", " ").capitalize(),
                kind="sub",
                sensitivity=top_cat.sensitivity,
                is_protected=False,
                status="active",
                created_by="system",
                centroid=embed_text(f"{top_cat.label_en} {subcategory_slug}"),
            )
    return top_cat, sub_cat


def models_q_teacher_or_global(teacher: TeacherProfile):
    from django.db.models import Q
    return Q(teacher=teacher) | Q(teacher__isnull=True)


def update_category_centroid(category: MemoryCategory, teacher: TeacherProfile | None = None) -> None:
    """
    Recompute category centroid from active memories linked to it for dynamic/teacher categories.
    Protected global core categories keep their canonical seed centroid so outlier memories
    (e.g., an emergent life area temporarily filed under Profile) remain detectable.
    """
    if category.kind == "core" and category.is_protected and category.teacher_id is None:
        return
    links_qs = MemoryCategoryLink.objects.filter(
        category=category,
        valid_to__isnull=True,
        memory__status="active",
    ).select_related("memory")
    if teacher and category.teacher_id:
        links_qs = links_qs.filter(memory__teacher=teacher)
    vectors = [link.memory.embedding for link in links_qs if link.memory.embedding]
    if vectors:
        category.centroid = compute_centroid(vectors)
        category.last_memory_at = timezone.now()
        category.save(update_fields=["centroid", "last_memory_at"])


def regenerate_core_profile(teacher: TeacherProfile | str) -> CoreProfile:
    """
    Build the compact always-injected CoreProfile (max ~300 tokens) from active memories in
    Profile, Teaching context, Preferences, and active Life Areas.
    Caches the rendered profile in Redis/Django cache.
    """
    if isinstance(teacher, str):
        teacher = get_or_create_teacher(teacher)

    active_links = (
        MemoryCategoryLink.objects.filter(
            memory__teacher=teacher,
            memory__status="active",
            valid_to__isnull=True,
        )
        .select_related("memory", "category", "subcategory")
        .order_by("category__kind", "category__slug", "-memory__recorded_at")
    )

    sections: dict[str, list[str]] = {
        "Profile": [],
        "Teaching context": [],
        "Preferences": [],
        "Active life areas": [],
    }
    built_from_ids: list[str] = []

    for link in active_links:
        mem = link.memory
        cat = link.category
        if cat.slug == "profile":
            sections["Profile"].append(mem.statement)
            built_from_ids.append(str(mem.id))
        elif cat.slug == "teaching_context":
            sections["Teaching context"].append(mem.statement)
            built_from_ids.append(str(mem.id))
        elif cat.slug == "preferences":
            sections["Preferences"].append(mem.statement)
            built_from_ids.append(str(mem.id))
        elif cat.kind == "life_area" and cat.status == "active":
            line = f"{cat.label_en}: {mem.statement}"
            if not any(existing.startswith(f"{cat.label_en}:") for existing in sections["Active life areas"]):
                sections["Active life areas"].append(line)
                built_from_ids.append(str(mem.id))

    lines: list[str] = []
    for header, items in sections.items():
        if items:
            joined = "; ".join(items[:4])
            lines.append(f"- {header}: {joined}")

    summary_text = "\n".join(lines)
    # Enforce ~300 token budget (~1200 chars)
    words = summary_text.split()
    if len(words) > CORE_PROFILE_MAX_TOKENS:
        summary_text = " ".join(words[:CORE_PROFILE_MAX_TOKENS]) + "..."

    profile, _ = CoreProfile.objects.get_or_create(teacher=teacher)
    profile.summary = summary_text
    profile.built_from = built_from_ids
    profile.version = (profile.version or 0) + 1
    profile.save()

    cache.set(f"amal:core_profile:{teacher.teacher_id}", summary_text, timeout=86400)
    return profile


def _create_or_group_notification(
    teacher: TeacherProfile,
    memory: MemoryItem,
    category_slug: str,
    kind: str,
    title: str,
    body: str = "",
    diff_before: str = "",
    diff_after: str = "",
    origin_surface: str = "web",
) -> MemoryNotification:
    """
    Create a web notification for a saved/updated memory or consent card.
    Enforces the 'No spam: at most one banner per 60 seconds; several saves are grouped into one banner' rule.
    """
    now = timezone.now()
    if kind in ("saved", "updated"):
        window_start = now - timedelta(seconds=BANNER_GROUP_WINDOW_SECONDS)
        recent_banner = (
            MemoryNotification.objects.filter(
                teacher=teacher,
                kind__in=["saved", "updated"],
                action="pending",
                seen_at__isnull=True,
                created_at__gte=window_start,
            )
            .order_by("-created_at")
            .first()
        )
        if recent_banner:
            grouped = list(recent_banner.grouped_items or [])
            if not grouped and recent_banner.memory_id:
                grouped.append(
                    {
                        "memory_id": str(recent_banner.memory_id),
                        "title": recent_banner.title,
                        "category_slug": recent_banner.category_slug,
                    }
                )
            grouped.append(
                {
                    "memory_id": str(memory.id),
                    "title": title,
                    "category_slug": category_slug,
                }
            )
            recent_banner.grouped_items = grouped
            recent_banner.grouped_count = len(grouped)
            recent_banner.memory = memory
            recent_banner.title = f"Amal remembered {len(grouped)} things ({memory.statement})"
            recent_banner.body = " · ".join(item["title"] for item in grouped)
            recent_banner.save()
            return recent_banner

    return MemoryNotification.objects.create(
        teacher=teacher,
        memory=memory,
        category_slug=category_slug,
        kind=kind,
        title=title,
        body=body,
        diff_before=diff_before,
        diff_after=diff_after,
        origin_surface=origin_surface,
        grouped_count=1,
        grouped_items=[
            {
                "memory_id": str(memory.id),
                "title": title,
                "category_slug": category_slug,
            }
        ],
    )


def save_or_update_memory(
    teacher_id: str,
    statement: str,
    category_slug: str | None = None,
    subcategory_slug: str | None = None,
    source: str = "stated",
    confidence: float = 0.95,
    salience: float = 0.80,
    surface: str = "whatsapp",
    product_area: str = "chat",
    conversation_id: str = "conv-default",
    message_id: str = "msg-1",
    quote_span: str = "0:0",
    created_by: str = "live_pass",
    explicit_consent_granted: bool = False,
    valid_from=None,
) -> dict[str, Any]:
    """
    Core transactional write pipeline for saving or updating a teacher memory.
    Handles opt-out, safety guardrails, tombstone checks, consent routing,
    bi-temporal supersession, and atomic notification emission.
    """
    teacher = get_or_create_teacher(teacher_id)
    mem_settings = teacher.settings

    if not mem_settings.enabled:
        return {"saved": False, "status": "opted_out", "reason": "memory_disabled_by_teacher"}

    guard = check_guardrails(statement, source=source)
    if not guard.allowed:
        if guard.escalation_flow:
            MemoryEvent.objects.create(
                teacher=teacher,
                event=f"safety.{guard.escalation_flow}_triggered",
                actor=created_by,
                payload={"reason": guard.reason, "surface": surface},
            )
        return {
            "saved": False,
            "status": "blocked_by_guardrail",
            "reason": guard.reason,
            "escalation_flow": guard.escalation_flow,
        }

    inferred_cat, inferred_sub, inferred_sens, slot = infer_category_and_slot(
        statement,
        explicit_category=category_slug,
        explicit_subcategory=subcategory_slug,
    )
    top_cat, sub_cat = resolve_category_and_subcategory(teacher, inferred_cat, inferred_sub)

    # Reorganization/filing never lowers sensitivity: life areas are normal; consent categories force 'consent'
    sensitivity = "consent" if (top_cat.slug in CONSENT_CATEGORY_SLUGS or top_cat.sensitivity == "consent" or inferred_sens == "consent") else "normal"

    stmt_hmac = compute_statement_hmac(teacher.teacher_id, statement, slot)

    # 1. Tombstone check: exact match is blocked
    if MemoryTombstone.objects.filter(teacher=teacher, statement_hmac=stmt_hmac).exists():
        return {"saved": False, "status": "blocked_by_tombstone", "reason": "exact_tombstone_match"}

    # 2. Same-slot tombstone near-match -> require consent prompt instead of auto-saving
    same_slot_tombstone = MemoryTombstone.objects.filter(teacher=teacher, slot=slot).exists()
    if same_slot_tombstone and created_by != "teacher":
        sensitivity = "consent"

    # 3. Never ask twice about the same candidate item
    existing_consent = ConsentRequest.objects.filter(teacher=teacher, statement_hmac=stmt_hmac).first()
    if existing_consent and existing_consent.answer in ("no", "expired", "pending") and not explicit_consent_granted:
        return {
            "saved": False,
            "status": "consent_already_asked_or_declined",
            "consent_request_id": str(existing_consent.id),
        }

    # 4. Standing 'never_remember' setting for sensitive items
    if sensitivity == "consent" and mem_settings.sensitive_mode == "never_remember" and not explicit_consent_granted:
        return {"saved": False, "status": "blocked_by_sensitive_mode", "reason": "teacher_set_never_remember"}

    lang = detect_language(statement)
    vec = embed_text(statement)
    tokens_str = " ".join(simple_tokenize(statement))
    now = timezone.now()

    learner_pseudonym = ""
    stored_statement = format_memory_bullet_wording(statement)
    if top_cat.slug == "named_learners":
        learner_pseudonym, _raw_name = pseudonymize_learner_name(teacher.teacher_id, stored_statement)

    # 5. Deduplicate against existing active memories for this teacher
    active_memories = list(MemoryItem.objects.filter(teacher=teacher, status="active"))
    norm_new = normalize_statement(stored_statement)
    for existing in active_memories:
        if normalize_statement(existing.statement) == norm_new:
            existing.last_used_at = now
            existing.salience = min(1.0, existing.salience + 0.05)
            existing.save(update_fields=["last_used_at", "salience"])
            return {
                "saved": False,
                "status": "duplicate_confirmed",
                "memory_id": str(existing.id),
            }
        if (
            existing.slot == slot
            and cosine_similarity(existing.embedding, vec) >= 0.96
            and trigram_similarity(existing.statement, stored_statement) >= 0.75
        ):
            existing.last_used_at = now
            existing.save(update_fields=["last_used_at"])
            return {
                "saved": False,
                "status": "duplicate_confirmed",
                "memory_id": str(existing.id),
            }

    needs_consent = sensitivity == "consent" and not explicit_consent_granted and created_by != "teacher"
    target_status = "pending_consent" if needs_consent else "active"

    with transaction.atomic():
        superseded_old: MemoryItem | None = None
        if target_status == "active" and slot in SINGLETON_SLOTS:
            slot_existing = (
                MemoryItem.objects.filter(teacher=teacher, slot=slot, status="active")
                .order_by("-recorded_at")
                .first()
            )
            if slot_existing:
                # Teacher edits always win over later automated extraction
                if slot_existing.created_by == "teacher" and created_by != "teacher":
                    return {
                        "saved": False,
                        "status": "skipped_teacher_edit_precedence",
                        "memory_id": str(slot_existing.id),
                    }
                superseded_old = slot_existing

        new_item = MemoryItem.objects.create(
            teacher=teacher,
            scope="teacher",
            statement=stored_statement,
            slot=slot,
            learner_pseudonym_id=learner_pseudonym,
            lang=lang,
            source=source,
            sensitivity=sensitivity,
            status=target_status,
            confidence=confidence,
            salience=salience,
            embedding=vec,
            embed_model=getattr(settings, "AMAL_EMBED_MODEL", "AfriE5-Large-Instruct-halfvec1024"),
            tsv_tokens=tokens_str,
            valid_from=valid_from or now,
            recorded_at=now,
            created_by=created_by,
        )

        if superseded_old:
            superseded_old.status = "superseded"
            superseded_old.retired_at = now
            superseded_old.valid_to = valid_from or now
            superseded_old.superseded_by = new_item
            superseded_old.save(
                update_fields=["status", "retired_at", "valid_to", "superseded_by"]
            )
            MemoryCategoryLink.objects.filter(memory=superseded_old, valid_to__isnull=True).update(valid_to=now)

        MemoryCategoryLink.objects.create(
            memory=new_item,
            category=top_cat,
            subcategory=sub_cat,
            valid_from=now,
        )

        MemoryEvidence.objects.create(
            memory=new_item,
            surface=surface,
            product_area=product_area,
            conversation_id=conversation_id,
            message_id=message_id,
            quote_span=quote_span,
            extracted_by=created_by,
        )

        teacher.last_active_at = now
        teacher.save(update_fields=["last_active_at"])

        if needs_consent:
            if teacher.preferred_lang == "sw" or lang == "sw":
                prompt_text = f'Je, nikumbuke kwamba "{stored_statement}"? Jibu NDIO au HAPANA.'
            else:
                prompt_text = f'Should I remember that "{stored_statement}"? Reply YES or NO.'

            consent_req = ConsentRequest.objects.create(
                teacher=teacher,
                memory=new_item,
                statement_hmac=stmt_hmac,
                slot=slot,
                prompt_text=prompt_text,
                channel=surface,
                answer="pending",
            )
            MemoryEvent.objects.create(
                teacher=teacher,
                memory_id_ref=str(new_item.id),
                event="memory.consent_requested",
                actor=created_by,
                payload={"category": top_cat.slug, "surface": surface},
            )
            notification = _create_or_group_notification(
                teacher=teacher,
                memory=new_item,
                category_slug=top_cat.slug,
                kind="consent_prompt",
                title="Amal would like to remember this. Keep it?",
                body=stored_statement,
                origin_surface=surface,
            )
            return {
                "saved": True,
                "status": "pending_consent",
                "memory_id": str(new_item.id),
                "statement": stored_statement,
                "consent_request_id": str(consent_req.id),
                "consent_prompt": prompt_text,
                "notification_id": str(notification.id),
                "category": top_cat.slug,
                "subcategory": sub_cat.slug if sub_cat else "",
            }

        # Active normal memory (or consented memory)
        update_category_centroid(top_cat, teacher=teacher)
        if sub_cat:
            update_category_centroid(sub_cat, teacher=teacher)

        if superseded_old:
            event_name = "memory.updated"
            notif_kind = "updated"
            notif_title = f"Amal updated: {superseded_old.statement} → {stored_statement}"
            diff_before = superseded_old.statement
            diff_after = stored_statement
        else:
            event_name = "memory.saved"
            notif_kind = "saved"
            notif_title = f"Amal remembered: {stored_statement}"
            diff_before = ""
            diff_after = stored_statement

        MemoryEvent.objects.create(
            teacher=teacher,
            memory_id_ref=str(new_item.id),
            event=event_name,
            actor=created_by,
            payload={
                "category": top_cat.slug,
                "subcategory": sub_cat.slug if sub_cat else "",
                "surface": surface,
                "superseded_id": str(superseded_old.id) if superseded_old else None,
            },
        )

        notification = _create_or_group_notification(
            teacher=teacher,
            memory=new_item,
            category_slug=top_cat.slug,
            kind=notif_kind,
            title=notif_title,
            body=stored_statement,
            diff_before=diff_before,
            diff_after=diff_after,
            origin_surface=surface,
        )

        if top_cat.slug in CORE_PROFILE_CATEGORY_SLUGS or top_cat.kind == "life_area":
            regenerate_core_profile(teacher)

        return {
            "saved": True,
            "status": "active",
            "memory_id": str(new_item.id),
            "statement": stored_statement,
            "superseded_id": str(superseded_old.id) if superseded_old else None,
            "notification_id": str(notification.id),
            "category": top_cat.slug,
            "subcategory": sub_cat.slug if sub_cat else "",
        }


def resolve_consent_request(
    teacher_id: str,
    consent_request_id: str,
    answer: str,
) -> dict[str, Any]:
    """
    Resolve a pending ConsentRequest with 'yes', 'no', or 'expired'.
    - YES promotes the memory from `pending_consent` to `active`.
    - NO or EXPIRED hard-deletes the candidate memory and creates a tombstone so the agent never asks twice.
    """
    teacher = get_or_create_teacher(teacher_id)
    normalized_answer = answer.strip().lower()
    if normalized_answer in ("ndio", "yes", "y", "keep"):
        normalized_answer = "yes"
    elif normalized_answer in ("hapana", "no", "n", "delete", "remove"):
        normalized_answer = "no"
    elif normalized_answer != "expired":
        raise ValueError(f"Unsupported consent answer: {answer}")

    with transaction.atomic():
        consent_req = ConsentRequest.objects.select_for_update().get(
            id=consent_request_id,
            teacher=teacher,
        )
        now = timezone.now()
        mem = consent_req.memory

        if normalized_answer == "yes" and mem:
            mem.status = "active"
            mem.recorded_at = now
            mem.save(update_fields=["status", "recorded_at"])

            consent_req.answer = "yes"
            consent_req.answered_at = now
            consent_req.save(update_fields=["answer", "answered_at"])

            MemoryNotification.objects.filter(memory=mem, kind="consent_prompt").update(
                action="kept",
                seen_at=now,
            )

            MemoryEvent.objects.create(
                teacher=teacher,
                memory_id_ref=str(mem.id),
                event="memory.consent_accepted",
                actor="teacher",
                payload={"slot": consent_req.slot},
            )
            return {
                "resolved": True,
                "answer": "yes",
                "memory_id": str(mem.id),
                "status": "active",
            }
        else:
            # NO or EXPIRED -> hard delete candidate and record HMAC tombstone
            MemoryTombstone.objects.get_or_create(
                teacher=teacher,
                statement_hmac=consent_req.statement_hmac,
                defaults={"slot": consent_req.slot},
            )
            consent_req.answer = normalized_answer
            consent_req.answered_at = now
            consent_req.memory = None
            consent_req.save(update_fields=["answer", "answered_at", "memory"])

            if mem:
                MemoryNotification.objects.filter(memory=mem).delete()
                MemoryCategoryLink.objects.filter(memory=mem).delete()
                MemoryEvidence.objects.filter(memory=mem).delete()
                mem.delete()

            MemoryEvent.objects.create(
                teacher=teacher,
                memory_id_ref="",
                event=f"memory.consent_{normalized_answer}",
                actor="teacher" if normalized_answer == "no" else "system",
                payload={"slot": consent_req.slot},
            )
            return {
                "resolved": True,
                "answer": normalized_answer,
                "status": "deleted",
            }


def edit_memory(
    teacher_id: str,
    memory_id: str,
    new_statement: str,
    actor: str = "teacher",
) -> dict[str, Any]:
    """
    Bi-temporally supersede an existing memory with corrected text.
    Marks the old row `superseded` with `retired_at`, `valid_to`, and `superseded_by`.
    Teacher edits set `created_by='teacher'` so they always win over later extraction.
    """
    teacher = get_or_create_teacher(teacher_id)
    guard = check_guardrails(new_statement, source="stated")
    if not guard.allowed:
        return {"edited": False, "reason": guard.reason}

    with transaction.atomic():
        old_mem = MemoryItem.objects.select_for_update().get(id=memory_id, teacher=teacher)
        active_link = (
            MemoryCategoryLink.objects.filter(memory=old_mem, valid_to__isnull=True)
            .select_related("category", "subcategory")
            .first()
        )
        cat = active_link.category if active_link else resolve_category_and_subcategory(teacher, "profile", "identity")[0]
        sub = active_link.subcategory if active_link else None

        now = timezone.now()
        formatted_new = format_memory_bullet_wording(new_statement)
        vec = embed_text(formatted_new)
        tokens_str = " ".join(simple_tokenize(formatted_new))

        new_mem = MemoryItem.objects.create(
            teacher=teacher,
            scope=old_mem.scope,
            statement=formatted_new,
            slot=old_mem.slot,
            learner_pseudonym_id=old_mem.learner_pseudonym_id,
            lang=detect_language(formatted_new),
            source="stated",
            sensitivity=old_mem.sensitivity,
            status="active",
            confidence=1.0 if actor == "teacher" else old_mem.confidence,
            salience=old_mem.salience,
            embedding=vec,
            embed_model=old_mem.embed_model,
            tsv_tokens=tokens_str,
            valid_from=now,
            recorded_at=now,
            created_by=actor,
        )

        old_mem.status = "superseded"
        old_mem.retired_at = now
        old_mem.valid_to = now
        old_mem.superseded_by = new_mem
        old_mem.save(update_fields=["status", "retired_at", "valid_to", "superseded_by"])

        if active_link:
            active_link.valid_to = now
            active_link.save(update_fields=["valid_to"])

        MemoryCategoryLink.objects.create(
            memory=new_mem,
            category=cat,
            subcategory=sub,
            valid_from=now,
        )

        MemoryNotification.objects.filter(memory=old_mem).update(
            memory=new_mem,
            action="edited",
            title=f"Edited: {new_statement.strip()}",
            body=new_statement.strip(),
            seen_at=now,
        )

        MemoryEvent.objects.create(
            teacher=teacher,
            memory_id_ref=str(new_mem.id),
            event="memory.edited",
            actor=actor,
            payload={
                "old_memory_id": str(old_mem.id),
                "category": cat.slug,
            },
        )

        update_category_centroid(cat, teacher=teacher)
        regenerate_core_profile(teacher)

    return {
        "edited": True,
        "old_memory_id": str(old_mem.id),
        "new_memory_id": str(new_mem.id),
        "statement": new_mem.statement,
    }


def delete_memory(
    teacher_id: str,
    memory_id: str,
    actor: str = "teacher",
    record_tombstone: bool = True,
    is_undo: bool = False,
) -> dict[str, Any]:
    """
    Hard-delete a memory, its evidence, and its category links in one transaction.
    Stores a keyed HMAC tombstone (never text or embedding) and triggers derived store cleanup.
    """
    teacher = get_or_create_teacher(teacher_id)
    with transaction.atomic():
        mem = MemoryItem.objects.filter(id=memory_id, teacher=teacher).first()
        if not mem:
            return {"deleted": False, "reason": "not_found"}

        active_link = MemoryCategoryLink.objects.filter(memory=mem).select_related("category").first()
        cat_slug = active_link.category.slug if active_link else ""
        stmt_hmac = compute_statement_hmac(teacher.teacher_id, mem.statement, mem.slot)
        slot = mem.slot
        mem_id_str = str(mem.id)

        if record_tombstone:
            MemoryTombstone.objects.get_or_create(
                teacher=teacher,
                statement_hmac=stmt_hmac,
                defaults={"slot": slot},
            )

        # Redact notifications referencing this memory so no deleted text remains
        if is_undo:
            MemoryNotification.objects.filter(memory=mem).update(
                memory=None,
                title="Memory undone and removed",
                body="",
                diff_before="",
                diff_after="",
                action="undone",
                seen_at=timezone.now(),
            )
        else:
            MemoryNotification.objects.filter(memory=mem).delete()

        # Also remove any superseded chain items for this slot so no old copy remains
        MemoryItem.objects.filter(teacher=teacher, superseded_by=mem).delete()
        MemoryCategoryLink.objects.filter(memory=mem).delete()
        MemoryEvidence.objects.filter(memory=mem).delete()
        ConsentRequest.objects.filter(memory=mem).delete()
        mem.delete()

        # Append-only audit log holds NO deleted content after erasure
        MemoryEvent.objects.create(
            teacher=teacher,
            memory_id_ref=mem_id_str,
            event="memory.undone" if is_undo else "memory.deleted",
            actor=actor,
            payload={"category": cat_slug, "slot": slot},
        )

    from .tasks import purge_deleted_memory_derivatives
    purge_deleted_memory_derivatives.delay(teacher.teacher_id, mem_id_str)

    return {
        "deleted": True,
        "memory_id": mem_id_str,
        "tombstone_hmac": stmt_hmac,
    }


def delete_all_memories(teacher_id: str, actor: str = "teacher") -> dict[str, Any]:
    """Hard-delete all memories and derived state for a teacher."""
    teacher = get_or_create_teacher(teacher_id)
    with transaction.atomic():
        count = MemoryItem.objects.filter(teacher=teacher).count()
        MemoryCategoryLink.objects.filter(memory__teacher=teacher).delete()
        MemoryEvidence.objects.filter(memory__teacher=teacher).delete()
        ConsentRequest.objects.filter(teacher=teacher).delete()
        MemoryNotification.objects.filter(teacher=teacher).delete()
        MemoryItem.objects.filter(teacher=teacher).delete()
        MemoryCategory.objects.filter(teacher=teacher, kind__in=["life_area", "sub"]).delete()

        CoreProfile.objects.filter(teacher=teacher).update(summary="", built_from=[], version=1)
        cache.delete(f"amal:core_profile:{teacher.teacher_id}")

        MemoryEvent.objects.create(
            teacher=teacher,
            event="memory.deleted_all",
            actor=actor,
            payload={"deleted_count": count},
        )

    from .tasks import purge_deleted_memory_derivatives
    purge_deleted_memory_derivatives.delay(teacher.teacher_id, "all")

    return {"deleted_all": True, "deleted_count": count}


def set_memory_opt_out(teacher_id: str, enabled: bool) -> dict[str, Any]:
    """
    Pause/opt-out or re-enable memory.
    Opt-out stops extraction and retrieval immediately and schedules a full purge.
    """
    teacher = get_or_create_teacher(teacher_id)
    mem_settings = teacher.settings
    mem_settings.enabled = enabled
    mem_settings.save(update_fields=["enabled", "updated_at"])

    if not enabled:
        delete_all_memories(teacher_id, actor="teacher_opt_out")

    return {"teacher_id": teacher.teacher_id, "enabled": enabled}


def compute_aggregate_insights() -> dict[str, Any]:
    """
    Compute anonymized cohort (n >= 10) and global (n >= 50) insights.
    Reads ONLY from teachers with `enabled=True` and `share_aggregate=True`,
    and strictly excludes `consent` sensitivity categories (People, Wellbeing, Named learners).
    """
    seed_core_categories()
    eligible_teachers = TeacherProfile.objects.filter(
        settings__enabled=True,
        settings__share_aggregate=True,
    )
    eligible_ids = set(eligible_teachers.values_list("teacher_id", flat=True))

    links = (
        MemoryCategoryLink.objects.filter(
            valid_to__isnull=True,
            memory__status="active",
            memory__sensitivity="normal",
            memory__teacher_id__in=eligible_ids,
        )
        .exclude(category__slug__in=CONSENT_CATEGORY_SLUGS)
        .select_related("memory", "memory__teacher", "category")
    )

    # Group distinct teachers by (cohort_key, category_slug, slot) and (country:curriculum:lang, category_slug, slot)
    cohort_buckets: dict[tuple[str, str, str], set[str]] = {}
    global_buckets: dict[tuple[str, str, str], set[str]] = {}
    sample_statements: dict[tuple[str, str], str] = {}
    category_map: dict[str, MemoryCategory] = {}

    for link in links:
        t = link.memory.teacher
        cat_slug = link.category.slug
        if link.category.teacher_id is None:
            category_map[cat_slug] = link.category
        slot = link.memory.slot

        c_key = (t.cohort_key, cat_slug, slot)
        cohort_buckets.setdefault(c_key, set()).add(t.teacher_id)

        g_scope_key = f"{t.country}:{t.curriculum}:{link.memory.lang}"
        g_key = (g_scope_key, cat_slug, slot)
        global_buckets.setdefault(g_key, set()).add(t.teacher_id)

        sample_statements[(cat_slug, slot)] = link.memory.statement

    AggregateInsight.objects.all().delete()
    cohort_written = 0
    global_written = 0

    for (cohort_key, cat_slug, slot), teacher_set in cohort_buckets.items():
        if len(teacher_set) >= COHORT_MIN_TEACHERS and cat_slug in category_map:
            AggregateInsight.objects.create(
                scope="cohort",
                scope_key=cohort_key,
                category=category_map[cat_slug],
                statement=f"Many teachers in cohort {cohort_key} share pattern on {slot.replace('.', ' ')} ({len(teacher_set)} teachers)",
                n_teachers=len(teacher_set),
            )
            cohort_written += 1

    for (g_scope_key, cat_slug, slot), teacher_set in global_buckets.items():
        if len(teacher_set) >= GLOBAL_MIN_TEACHERS and cat_slug in category_map:
            AggregateInsight.objects.create(
                scope="global",
                scope_key=g_scope_key,
                category=category_map[cat_slug],
                statement=f"Across {g_scope_key}, {len(teacher_set)} teachers report needs in {slot.replace('.', ' ')}",
                n_teachers=len(teacher_set),
            )
            global_written += 1

    return {
        "cohort_insights_written": cohort_written,
        "global_insights_written": global_written,
    }


def compute_undo_quality_metrics() -> dict[str, Any]:
    """
    Calculate per-category undo/edit rates from MemoryNotification rows.
    Flags any category with an undo rate > 5% for extractor review (PRD line 271).
    """
    notifs = MemoryNotification.objects.exclude(category_slug="")
    by_cat: dict[str, dict[str, int]] = {}
    for n in notifs:
        stats = by_cat.setdefault(n.category_slug, {"total": 0, "undone": 0, "edited": 0})
        stats["total"] += 1
        if n.action == "undone":
            stats["undone"] += 1
        elif n.action == "edited":
            stats["edited"] += 1

    report: dict[str, Any] = {}
    flagged_categories: list[str] = []
    for slug, stats in by_cat.items():
        total = max(1, stats["total"])
        undo_rate = stats["undone"] / total
        edit_rate = stats["edited"] / total
        flagged = undo_rate > 0.05
        if flagged:
            flagged_categories.append(slug)
        report[slug] = {
            "total": stats["total"],
            "undone": stats["undone"],
            "edited": stats["edited"],
            "undo_rate": round(undo_rate, 4),
            "edit_rate": round(edit_rate, 4),
            "flagged_for_review": flagged,
        }

    return {
        "categories": report,
        "flagged_categories": flagged_categories,
    }
