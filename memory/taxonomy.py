"""
Taxonomy Evolution engine (three-layer hierarchy: Core Categories, Dynamic Life Areas, Subcategories).
Implements clustering, proposal generation, staged auto-application, reversible TaxonomyChangeset
diffs, one-step Undo with 30-day category freeze, and teacher-owned life area controls.
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import numpy as np
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from sklearn.cluster import AgglomerativeClustering

from .constants import (
    ARCHIVE_LIFE_AREA_INACTIVE_DAYS,
    CONSENT_CATEGORY_SLUGS,
    CREATE_SUBCATEGORY_MIN_OTHER_MEMORIES,
    MAX_ACTIVE_LIFE_AREAS_PER_TEACHER,
    MERGE_SUBCATEGORY_INACTIVE_DAYS,
    MERGE_SUBCATEGORY_MAX_MEMORIES,
    NEW_LIFE_AREA_MAX_CENTROID_SIMILARITY,
    NEW_LIFE_AREA_MIN_CONVERSATIONS,
    NEW_LIFE_AREA_MIN_MEMORIES,
    PROMOTE_GLOBAL_MIN_TEACHERS,
    REFILE_MAX_FRACTION_PER_NIGHT,
    REFILE_MIN_SIMILARITY_MARGIN,
    RENAME_COOLDOWN_DAYS,
    SPLIT_SUBCATEGORY_MIN_CLUSTER_SIZE,
    SPLIT_SUBCATEGORY_MIN_MEMORIES,
    UNDO_FREEZE_DAYS,
)
from .embeddings import (
    compute_centroid,
    cosine_similarity,
    embed_text,
    simple_tokenize,
)
from .models import (
    MemoryCategory,
    MemoryCategoryLink,
    MemoryEvent,
    MemoryItem,
    MemoryNotification,
    TaxonomyChangeset,
    TaxonomyOperation,
    TeacherProfile,
)
from .services import (
    get_or_create_teacher,
    regenerate_core_profile,
    seed_core_categories,
    update_category_centroid,
)

# Bilingual naming dictionary for emergent life areas and subcategories
EMERGENT_TOPIC_LEXICON: list[dict[str, Any]] = [
    {
        "slug": "masters_studies",
        "label_en": "Master's studies",
        "label_sw": "Masomo ya Uzamili",
        "sub_slug": "coursework_and_thesis",
        "sub_en": "Coursework & thesis",
        "sub_sw": "Kozi na Tasnifu",
        "keywords": {"master", "masters", "master's", "degree", "university", "thesis", "postgraduate", "dissertation", "research", "semester", "uzamili", "shahada", "chuo"},
    },
    {
        "slug": "school_football_coaching",
        "label_en": "School football coaching",
        "label_sw": "Ukocha wa Mpira wa Miguu",
        "sub_slug": "team_training",
        "sub_en": "Team training & matches",
        "sub_sw": "Mazoezi na Mechi",
        "keywords": {"football", "soccer", "coaching", "coach", "tournament", "match", "team", "athletics", "sports", "mpira", "miguu", "kocha", "mashindano"},
    },
    {
        "slug": "school_agriculture_project",
        "label_en": "School agriculture & garden",
        "label_sw": "Mradi wa Kilimo Shuleni",
        "sub_slug": "crop_and_poultry",
        "sub_en": "Crops & poultry",
        "sub_sw": "Mazao na Ufugaji",
        "keywords": {"garden", "farming", "agriculture", "poultry", "maize", "crops", "irrigation", "agribusiness", "kilimo", "bustani", "kuku", "mahindi"},
    },
    {
        "slug": "drama_and_music_club",
        "label_en": "Drama & music festival",
        "label_sw": "Tamasha la Sanaa na Muziki",
        "sub_slug": "rehearsals",
        "sub_en": "Rehearsals & scripts",
        "sub_sw": "Mazoezi ya Tamasha",
        "keywords": {"drama", "festival", "choir", "music", "theatre", "rehearsal", "performance", "script", "tamasha", "igizo", "kwaya", "muziki"},
    },
]

SUBCATEGORY_SPLIT_LEXICON: list[dict[str, Any]] = [
    {
        "slug": "equipment_and_devices",
        "label_en": "Equipment",
        "label_sw": "Vifaa vya Darasani",
        "keywords": {"projector", "laptop", "electricity", "socket", "computer", "radio", "speaker", "internet", "umeme", "kompyuta"},
    },
    {
        "slug": "learning_materials",
        "label_en": "Learning materials",
        "label_sw": "Nyenzo za Kujifunzia",
        "keywords": {"textbook", "textbooks", "manila", "charts", "flashcards", "chalkboard", "exercise", "books", "vitabu", "chati", "ubao"},
    },
]


def _is_category_frozen(cat: MemoryCategory, now=None) -> bool:
    now = now or timezone.now()
    return bool(cat.frozen_until and cat.frozen_until > now)


def _infer_emergent_topic(statements: list[str]) -> dict[str, str]:
    """Name a new life area or subcategory in English and Kiswahili from its cluster statements."""
    token_bag: set[str] = set()
    for s in statements:
        token_bag.update(simple_tokenize(s))

    best_match = None
    best_overlap = 0
    for entry in EMERGENT_TOPIC_LEXICON:
        overlap = len(token_bag & entry["keywords"])
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = entry

    if best_match and best_overlap > 0:
        return {
            "slug": best_match["slug"],
            "label_en": best_match["label_en"],
            "label_sw": best_match["label_sw"],
            "sub_slug": best_match["sub_slug"],
            "sub_en": best_match["sub_en"],
            "sub_sw": best_match["sub_sw"],
        }

    # Fallback: pick top frequent content words
    stop = {"the", "and", "for", "with", "that", "has", "from", "into", "about", "teacher", "teaches", "school"}
    counts: dict[str, int] = {}
    for s in statements:
        for tok in simple_tokenize(s):
            if len(tok) >= 4 and tok not in stop:
                counts[tok] = counts.get(tok, 0) + 1
    top_words = [w for w, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:2]] or ["special", "interest"]
    slug = "_".join(top_words)
    title_en = " ".join(w.capitalize() for w in top_words)
    return {
        "slug": f"area_{slug}",
        "label_en": title_en,
        "label_sw": f"Eneo: {title_en}",
        "sub_slug": f"{slug}_general",
        "sub_en": f"{title_en} notes",
        "sub_sw": f"Maelezo ya {title_en}",
    }


def _cluster_embeddings(vectors: list[list[float]], distance_threshold: float = 0.55) -> list[list[int]]:
    """
    Cluster memory embeddings using Agglomerative Clustering with cosine distance.
    Returns a list of clusters, each containing indices into `vectors`.
    """
    if len(vectors) < 2:
        return [list(range(len(vectors)))] if vectors else []
    arr = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms < 1e-8] = 1.0
    normed = arr / norms

    clustering = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=distance_threshold,
    )
    labels = clustering.fit_predict(normed)
    clusters: dict[int, list[int]] = {}
    for idx, lbl in enumerate(labels):
        clusters.setdefault(int(lbl), []).append(idx)
    return sorted(clusters.values(), key=len, reverse=True)


def run_taxonomy_evolution_for_teacher(
    teacher_id: str,
    stage: str | None = None,
) -> dict[str, Any]:
    """
    Evaluate all Taxonomy Evolution rules for a teacher and build a versioned `TaxonomyChangeset`.
    Depending on `stage` ('phase2_propose_only', 'phase3_low_risk_auto', 'phase3_full_auto'),
    either leaves the changeset as 'proposed' for admin review or applies allowed operations
    atomically and emits one batched nightly notification card with Undo.
    """
    teacher = get_or_create_teacher(teacher_id)
    core_cats = seed_core_categories()
    effective_stage = stage or getattr(settings, "AMAL_TAXONOMY_STAGE", "phase3_full_auto")
    now = timezone.now()

    active_links = list(
        MemoryCategoryLink.objects.filter(
            memory__teacher=teacher,
            memory__status="active",
            valid_to__isnull=True,
        ).select_related("memory", "category", "subcategory")
    )
    if not active_links:
        return {"changeset_id": None, "operations": [], "applied": False}

    proposed_ops: list[dict[str, Any]] = []

    # Current active life areas for this teacher
    life_areas = list(
        MemoryCategory.objects.filter(
            teacher=teacher,
            kind="life_area",
            status="active",
        ).order_by("created_at")
    )
    all_top_cats = list(core_cats.values()) + life_areas

    # -------------------------------------------------------------------------
    # 1. ARCHIVE LIFE AREA: No new memory in the area for 90 days
    # -------------------------------------------------------------------------
    cutoff_archive = now - timedelta(days=ARCHIVE_LIFE_AREA_INACTIVE_DAYS)
    for la in list(life_areas):
        if _is_category_frozen(la, now):
            continue
        latest_link = (
            MemoryCategoryLink.objects.filter(
                category=la,
                valid_to__isnull=True,
                memory__status="active",
            )
            .order_by("-memory__recorded_at")
            .first()
        )
        last_ts = latest_link.memory.recorded_at if latest_link else la.last_memory_at or la.created_at
        if last_ts and last_ts < cutoff_archive:
            proposed_ops.append(
                {
                    "op_type": "archive_life_area",
                    "target_category_id": str(la.id),
                    "before_state": {"status": la.status, "label_en": la.label_en},
                    "after_state": {"status": "archived", "label_en": la.label_en},
                    "risk": "high",
                }
            )
            life_areas.remove(la)

    # -------------------------------------------------------------------------
    # 2. MERGE LIFE AREAS: Two life areas become near-duplicates (sim >= 0.80)
    #    Guard: Teacher-created names are never overwritten; older name kept otherwise.
    # -------------------------------------------------------------------------
    merged_la_ids: set[str] = set()
    for i in range(len(life_areas)):
        for j in range(i + 1, len(life_areas)):
            la_a = life_areas[i]
            la_b = life_areas[j]
            if str(la_a.id) in merged_la_ids or str(la_b.id) in merged_la_ids:
                continue
            if _is_category_frozen(la_a, now) or _is_category_frozen(la_b, now):
                continue
            sim = cosine_similarity(la_a.centroid, la_b.centroid)
            if sim >= 0.80:
                # Teacher-created name always wins; otherwise older life area wins
                if la_b.created_by == "teacher" and la_a.created_by != "teacher":
                    keeper, source_la = la_b, la_a
                else:
                    keeper, source_la = la_a, la_b
                source_links = [
                    str(lnk.memory_id)
                    for lnk in active_links
                    if lnk.category_id == source_la.id
                ]
                proposed_ops.append(
                    {
                        "op_type": "merge_life_areas",
                        "target_category_id": str(keeper.id),
                        "before_state": {
                            "source_category_id": str(source_la.id),
                            "source_label_en": source_la.label_en,
                            "keeper_category_id": str(keeper.id),
                            "keeper_label_en": keeper.label_en,
                            "memory_ids": source_links,
                        },
                        "after_state": {
                            "merged_into_id": str(keeper.id),
                            "keeper_label_en": keeper.label_en,
                        },
                        "risk": "high",
                    }
                )
                merged_la_ids.add(str(source_la.id))

    # -------------------------------------------------------------------------
    # 3. NEW LIFE AREA: >= 5 memories from >= 2 conversations about a topic
    #    whose similarity to every existing core category centroid is < 0.50.
    #    Guard: Never for consent categories; cap of 8 active life areas.
    # -------------------------------------------------------------------------
    if len(life_areas) - len(merged_la_ids) < MAX_ACTIVE_LIFE_AREAS_PER_TEACHER:
        outlier_links: list[MemoryCategoryLink] = []
        core_centroids = [c.centroid for c in core_cats.values() if c.centroid]
        for lnk in active_links:
            mem = lnk.memory
            if mem.sensitivity == "consent" or lnk.category.slug in CONSENT_CATEGORY_SLUGS:
                continue
            if lnk.category.kind == "life_area":
                continue
            max_core_sim = max(
                (cosine_similarity(mem.embedding, c_vec) for c_vec in core_centroids),
                default=0.0,
            )
            if max_core_sim < NEW_LIFE_AREA_MAX_CENTROID_SIMILARITY:
                outlier_links.append(lnk)

        if len(outlier_links) >= NEW_LIFE_AREA_MIN_MEMORIES:
            clusters = _cluster_embeddings(
                [lnk.memory.embedding for lnk in outlier_links],
                distance_threshold=0.45,
            )
            for cluster_indices in clusters:
                if len(cluster_indices) < NEW_LIFE_AREA_MIN_MEMORIES:
                    continue
                cluster_links = [outlier_links[idx] for idx in cluster_indices]
                conv_ids = set()
                for cl in cluster_links:
                    ev = cl.memory.evidence.first()
                    conv_ids.add(ev.conversation_id if ev else f"conv-{cl.memory_id}")
                if len(conv_ids) < NEW_LIFE_AREA_MIN_CONVERSATIONS:
                    continue

                topic_info = _infer_emergent_topic([cl.memory.statement for cl in cluster_links])
                # Check if life area with this slug already exists
                if MemoryCategory.objects.filter(teacher=teacher, slug=topic_info["slug"], status="active").exists():
                    continue

                proposed_ops.append(
                    {
                        "op_type": "create_life_area",
                        "target_category_id": None,
                        "before_state": {
                            "memory_ids": [str(cl.memory_id) for cl in cluster_links],
                            "previous_categories": {
                                str(cl.memory_id): {
                                    "category_id": str(cl.category_id),
                                    "subcategory_id": str(cl.subcategory_id) if cl.subcategory_id else None,
                                }
                                for cl in cluster_links
                            },
                        },
                        "after_state": {
                            "slug": topic_info["slug"],
                            "label_en": topic_info["label_en"],
                            "label_sw": topic_info["label_sw"],
                            "sub_slug": topic_info["sub_slug"],
                            "sub_en": topic_info["sub_en"],
                            "sub_sw": topic_info["sub_sw"],
                            "memory_ids": [str(cl.memory_id) for cl in cluster_links],
                        },
                        "risk": "high",
                    }
                )
                break

    # -------------------------------------------------------------------------
    # 4. RE-FILE: Memory is clearly closer to another category's centroid
    #    (similarity margin >= 0.10).
    #    Guards: Max 20% of a teacher's memories move per night;
    #            never lowers sensitivity (cannot move out of a consent category).
    # -------------------------------------------------------------------------
    max_refile_count = max(1, int(len(active_links) * REFILE_MAX_FRACTION_PER_NIGHT))
    refile_candidates: list[tuple[float, MemoryCategoryLink, MemoryCategory]] = []
    already_moving_ids = {
        mid
        for op in proposed_ops
        for mid in op.get("after_state", {}).get("memory_ids", [])
    }

    for lnk in active_links:
        if str(lnk.memory_id) in already_moving_ids:
            continue
        if _is_category_frozen(lnk.category, now):
            continue
        # Never move a memory out of a consent category without teacher action
        if lnk.category.slug in CONSENT_CATEGORY_SLUGS or lnk.memory.sensitivity == "consent":
            continue

        current_sim = cosine_similarity(lnk.memory.embedding, lnk.category.centroid)
        best_cat = lnk.category
        best_sim = current_sim
        for candidate_cat in all_top_cats:
            if candidate_cat.id == lnk.category_id or _is_category_frozen(candidate_cat, now):
                continue
            sim = cosine_similarity(lnk.memory.embedding, candidate_cat.centroid)
            if sim > best_sim:
                best_sim = sim
                best_cat = candidate_cat

        margin = best_sim - current_sim
        if best_cat.id != lnk.category_id and margin >= REFILE_MIN_SIMILARITY_MARGIN:
            refile_candidates.append((margin, lnk, best_cat))

    refile_candidates.sort(key=lambda x: x[0], reverse=True)
    for margin, lnk, best_cat in refile_candidates[:max_refile_count]:
        proposed_ops.append(
            {
                "op_type": "refile",
                "target_category_id": str(best_cat.id),
                "before_state": {
                    "memory_id": str(lnk.memory_id),
                    "from_category_id": str(lnk.category_id),
                    "from_category_label": lnk.category.label_en,
                    "from_subcategory_id": str(lnk.subcategory_id) if lnk.subcategory_id else None,
                },
                "after_state": {
                    "memory_id": str(lnk.memory_id),
                    "to_category_id": str(best_cat.id),
                    "to_category_label": best_cat.label_en,
                    "margin": round(margin, 4),
                },
                "risk": "low",
            }
        )

    # -------------------------------------------------------------------------
    # 5. SPLIT SUBCATEGORY: > 12 memories in a subcategory forming >= 2 clusters
    #    with >= 4 memories each.
    # -------------------------------------------------------------------------
    by_sub: dict[str, list[MemoryCategoryLink]] = {}
    for lnk in active_links:
        if lnk.subcategory_id:
            by_sub.setdefault(str(lnk.subcategory_id), []).append(lnk)

    for sub_id, sub_links in by_sub.items():
        if len(sub_links) <= SPLIT_SUBCATEGORY_MIN_MEMORIES:
            continue
        sub_cat = sub_links[0].subcategory
        parent_cat = sub_links[0].category
        if not sub_cat or _is_category_frozen(sub_cat, now) or _is_category_frozen(parent_cat, now):
            continue
        # Respect 30-day no-resplit guard
        if sub_cat.last_split_at and (now - sub_cat.last_split_at).days < MERGE_SUBCATEGORY_INACTIVE_DAYS:
            continue

        clusters = _cluster_embeddings(
            [lnk.memory.embedding for lnk in sub_links],
            distance_threshold=0.45,
        )
        valid_clusters = [c for c in clusters if len(c) >= SPLIT_SUBCATEGORY_MIN_CLUSTER_SIZE]
        if len(valid_clusters) >= 2:
            new_subs_spec: list[dict[str, Any]] = []
            for c_idx, indices in enumerate(valid_clusters[:2]):
                c_links = [sub_links[i] for i in indices]
                c_tokens = {t for cl in c_links for t in simple_tokenize(cl.memory.statement)}
                matched_lex = None
                for lex in SUBCATEGORY_SPLIT_LEXICON:
                    if c_tokens & lex["keywords"]:
                        matched_lex = lex
                        break
                if matched_lex and not any(s["slug"] == matched_lex["slug"] for s in new_subs_spec):
                    new_subs_spec.append(
                        {
                            "slug": matched_lex["slug"],
                            "label_en": matched_lex["label_en"],
                            "label_sw": matched_lex["label_sw"],
                            "memory_ids": [str(cl.memory_id) for cl in c_links],
                        }
                    )
                else:
                    topic = _infer_emergent_topic([cl.memory.statement for cl in c_links])
                    new_subs_spec.append(
                        {
                            "slug": f"{sub_cat.slug}_part_{c_idx + 1}",
                            "label_en": topic["label_en"],
                            "label_sw": topic["label_sw"],
                            "memory_ids": [str(cl.memory_id) for cl in c_links],
                        }
                    )

            proposed_ops.append(
                {
                    "op_type": "split_subcategory",
                    "target_category_id": str(parent_cat.id),
                    "before_state": {
                        "parent_category_id": str(parent_cat.id),
                        "parent_label_en": parent_cat.label_en,
                        "old_subcategory_id": str(sub_cat.id),
                        "old_subcategory_label": sub_cat.label_en,
                        "memory_ids": [str(cl.memory_id) for cl in sub_links],
                    },
                    "after_state": {
                        "parent_category_id": str(parent_cat.id),
                        "new_subcategories": new_subs_spec,
                    },
                    "risk": "high",
                }
            )

    # -------------------------------------------------------------------------
    # 6. CREATE SUBCATEGORY: >= 5 "general"/"other" memories under a category
    #    form a coherent cluster.
    # -------------------------------------------------------------------------
    by_other: dict[str, list[MemoryCategoryLink]] = {}
    for lnk in active_links:
        if not lnk.subcategory or lnk.subcategory.slug in ("general", "other"):
            by_other.setdefault(str(lnk.category_id), []).append(lnk)

    for cat_id, other_links in by_other.items():
        if len(other_links) < CREATE_SUBCATEGORY_MIN_OTHER_MEMORIES:
            continue
        parent_cat = other_links[0].category
        if _is_category_frozen(parent_cat, now):
            continue
        topic = _infer_emergent_topic([cl.memory.statement for cl in other_links])
        existing_names = set(
            MemoryCategory.objects.filter(parent=parent_cat, status="active").values_list("slug", flat=True)
        )
        sub_slug = topic["sub_slug"]
        if sub_slug in existing_names:
            continue
        proposed_ops.append(
            {
                "op_type": "create_subcategory",
                "target_category_id": str(parent_cat.id),
                "before_state": {
                    "parent_category_id": str(parent_cat.id),
                    "memory_ids": [str(cl.memory_id) for cl in other_links],
                    "previous_subcategory_ids": {
                        str(cl.memory_id): str(cl.subcategory_id) if cl.subcategory_id else None
                        for cl in other_links
                    },
                },
                "after_state": {
                    "parent_category_id": str(parent_cat.id),
                    "slug": sub_slug,
                    "label_en": topic["sub_en"],
                    "label_sw": topic["sub_sw"],
                    "memory_ids": [str(cl.memory_id) for cl in other_links],
                },
                "risk": "low",
            }
        )

    if not proposed_ops:
        return {"changeset_id": None, "operations": [], "applied": False}

    # Filter operations according to staged rollout mode
    if effective_stage == "phase2_propose_only":
        ops_to_record = proposed_ops
        auto_apply = False
    elif effective_stage == "phase3_low_risk_auto":
        ops_to_record = [op for op in proposed_ops if op.get("risk") == "low"] or proposed_ops
        auto_apply = all(op.get("risk") == "low" for op in ops_to_record)
    else:
        ops_to_record = proposed_ops
        auto_apply = True

    with transaction.atomic():
        summary_en, summary_sw = _summarize_operations(ops_to_record)
        changeset = TaxonomyChangeset.objects.create(
            teacher=teacher,
            source="dreaming",
            status="proposed",
            summary_en=summary_en,
            summary_sw=summary_sw,
        )
        for idx, op_spec in enumerate(ops_to_record):
            target_cat = (
                MemoryCategory.objects.filter(id=op_spec["target_category_id"]).first()
                if op_spec.get("target_category_id")
                else None
            )
            TaxonomyOperation.objects.create(
                changeset=changeset,
                seq=idx,
                op_type=op_spec["op_type"],
                target_category=target_cat,
                before_state=op_spec["before_state"],
                after_state=op_spec["after_state"],
            )

        if auto_apply:
            apply_taxonomy_changeset(str(changeset.id))
            changeset.refresh_from_db()

    return {
        "changeset_id": str(changeset.id),
        "status": changeset.status,
        "summary_en": changeset.summary_en,
        "operations": [op["op_type"] for op in ops_to_record],
        "applied": changeset.status == "applied",
    }


def _summarize_operations(ops: list[dict[str, Any]]) -> tuple[str, str]:
    """Generate human-friendly batched card text in English and Kiswahili."""
    for op in ops:
        if op["op_type"] == "create_life_area":
            label_en = op["after_state"]["label_en"]
            label_sw = op["after_state"]["label_sw"]
            return (
                f"Amal started a new area for you: {label_en}",
                f"Amal imeanzisha eneo jipya kwako: {label_sw}",
            )
        if op["op_type"] == "split_subcategory":
            parent_label = op["before_state"]["parent_label_en"]
            old_sub = op["before_state"]["old_subcategory_label"]
            new_names = " and ".join(s["label_en"] for s in op["after_state"]["new_subcategories"])
            return (
                f"Amal reorganized your {parent_label} memories: {old_sub} is now {new_names}",
                f"Amal imepanga upya kumbukumbu zako za {parent_label}: {old_sub} sasa ni {new_names}",
            )
        if op["op_type"] == "merge_life_areas":
            src = op["before_state"]["source_label_en"]
            keep = op["after_state"]["keeper_label_en"]
            return (
                f"Amal merged life area '{src}' into '{keep}'",
                f"Amal imeunganisha eneo '{src}' ndani ya '{keep}'",
            )
    return (
        f"Amal reorganized {len(ops)} memory category item(s)",
        f"Amal imepanga upya vipengele {len(ops)} vya kumbukumbu",
    )


def apply_taxonomy_changeset(changeset_id: str) -> dict[str, Any]:
    """
    Apply a `TaxonomyChangeset` atomically:
    Closes old `MemoryCategoryLink` rows (`valid_to=now`) and opens new ones (`changeset=changeset`).
    Emits one batched `MemoryNotification(kind='taxonomy_change')` per night and regenerates `CoreProfile`.
    """
    with transaction.atomic():
        changeset = TaxonomyChangeset.objects.select_for_update().get(id=changeset_id)
        if changeset.status == "applied":
            return {"applied": True, "changeset_id": str(changeset.id)}

        teacher = changeset.teacher
        now = timezone.now()

        for op in changeset.operations.all().order_by("seq"):
            if op.op_type == "create_life_area" and teacher:
                after = op.after_state
                life_area = MemoryCategory.objects.create(
                    teacher=teacher,
                    parent=None,
                    slug=after["slug"],
                    label_en=after["label_en"],
                    label_sw=after.get("label_sw", after["label_en"]),
                    kind="life_area",
                    sensitivity="normal",
                    is_protected=False,
                    status="active",
                    created_by="dreaming",
                    last_memory_at=now,
                )
                sub_cat = MemoryCategory.objects.create(
                    teacher=teacher,
                    parent=life_area,
                    slug=after.get("sub_slug", "general"),
                    label_en=after.get("sub_en", "General"),
                    label_sw=after.get("sub_sw", "Jumla"),
                    kind="sub",
                    sensitivity="normal",
                    is_protected=False,
                    status="active",
                    created_by="dreaming",
                    last_memory_at=now,
                )
                after["created_life_area_id"] = str(life_area.id)
                after["created_subcategory_id"] = str(sub_cat.id)
                op.target_category = life_area
                op.after_state = after
                op.save(update_fields=["target_category", "after_state"])

                mem_ids = after.get("memory_ids", [])
                MemoryCategoryLink.objects.filter(
                    memory_id__in=mem_ids,
                    valid_to__isnull=True,
                ).update(valid_to=now)

                for mid in mem_ids:
                    MemoryCategoryLink.objects.create(
                        memory_id=mid,
                        category=life_area,
                        subcategory=sub_cat,
                        valid_from=now,
                        changeset=changeset,
                    )
                update_category_centroid(life_area, teacher=teacher)
                update_category_centroid(sub_cat, teacher=teacher)

            elif op.op_type == "archive_life_area" and op.target_category:
                cat = op.target_category
                cat.status = "archived"
                cat.save(update_fields=["status"])

            elif op.op_type == "merge_life_areas" and op.target_category:
                keeper = op.target_category
                src_id = op.before_state.get("source_category_id")
                src_cat = MemoryCategory.objects.filter(id=src_id).first()
                mem_ids = op.before_state.get("memory_ids", [])
                if src_cat:
                    src_cat.status = "merged"
                    src_cat.merged_into = keeper
                    src_cat.save(update_fields=["status", "merged_into"])
                MemoryCategoryLink.objects.filter(
                    memory_id__in=mem_ids,
                    valid_to__isnull=True,
                ).update(valid_to=now)
                for mid in mem_ids:
                    MemoryCategoryLink.objects.create(
                        memory_id=mid,
                        category=keeper,
                        valid_from=now,
                        changeset=changeset,
                    )
                if teacher:
                    update_category_centroid(keeper, teacher=teacher)

            elif op.op_type == "refile" and op.target_category:
                to_cat = op.target_category
                mid = op.after_state.get("memory_id")
                MemoryCategoryLink.objects.filter(
                    memory_id=mid,
                    valid_to__isnull=True,
                ).update(valid_to=now)
                MemoryCategoryLink.objects.create(
                    memory_id=mid,
                    category=to_cat,
                    valid_from=now,
                    changeset=changeset,
                )
                if teacher:
                    update_category_centroid(to_cat, teacher=teacher)

            elif op.op_type == "split_subcategory" and op.target_category:
                parent_cat = op.target_category
                old_sub_id = op.before_state.get("old_subcategory_id")
                old_sub = MemoryCategory.objects.filter(id=old_sub_id).first()
                if old_sub:
                    old_sub.status = "archived"
                    old_sub.last_split_at = now
                    old_sub.save(update_fields=["status", "last_split_at"])

                created_sub_ids: list[str] = []
                for sub_spec in op.after_state.get("new_subcategories", []):
                    new_sub = MemoryCategory.objects.create(
                        teacher=teacher,
                        parent=parent_cat,
                        slug=sub_spec["slug"],
                        label_en=sub_spec["label_en"],
                        label_sw=sub_spec.get("label_sw", sub_spec["label_en"]),
                        kind="sub",
                        sensitivity=parent_cat.sensitivity,
                        is_protected=False,
                        status="active",
                        created_by="dreaming",
                        last_split_at=now,
                        last_memory_at=now,
                    )
                    created_sub_ids.append(str(new_sub.id))
                    mids = sub_spec.get("memory_ids", [])
                    MemoryCategoryLink.objects.filter(
                        memory_id__in=mids,
                        valid_to__isnull=True,
                    ).update(valid_to=now)
                    for mid in mids:
                        MemoryCategoryLink.objects.create(
                            memory_id=mid,
                            category=parent_cat,
                            subcategory=new_sub,
                            valid_from=now,
                            changeset=changeset,
                        )
                    update_category_centroid(new_sub, teacher=teacher)

                after = dict(op.after_state)
                after["created_subcategory_ids"] = created_sub_ids
                op.after_state = after
                op.save(update_fields=["after_state"])

            elif op.op_type == "create_subcategory" and op.target_category:
                parent_cat = op.target_category
                after = dict(op.after_state)
                new_sub = MemoryCategory.objects.create(
                    teacher=teacher,
                    parent=parent_cat,
                    slug=after["slug"],
                    label_en=after["label_en"],
                    label_sw=after.get("label_sw", after["label_en"]),
                    kind="sub",
                    sensitivity=parent_cat.sensitivity,
                    is_protected=False,
                    status="active",
                    created_by="dreaming",
                    last_memory_at=now,
                )
                after["created_subcategory_id"] = str(new_sub.id)
                op.after_state = after
                op.save(update_fields=["after_state"])

                mids = after.get("memory_ids", [])
                MemoryCategoryLink.objects.filter(
                    memory_id__in=mids,
                    valid_to__isnull=True,
                ).update(valid_to=now)
                for mid in mids:
                    MemoryCategoryLink.objects.create(
                        memory_id=mid,
                        category=parent_cat,
                        subcategory=new_sub,
                        valid_from=now,
                        changeset=changeset,
                    )
                update_category_centroid(new_sub, teacher=teacher)

        changeset.status = "applied"
        changeset.applied_at = now
        changeset.save(update_fields=["status", "applied_at"])

        if teacher:
            regenerate_core_profile(teacher)
            MemoryNotification.objects.create(
                teacher=teacher,
                changeset=changeset,
                kind="taxonomy_change",
                title=changeset.summary_en,
                body=changeset.summary_sw,
                origin_surface="dreaming",
            )
            MemoryEvent.objects.create(
                teacher=teacher,
                event="taxonomy.changeset_applied",
                actor="dreaming",
                payload={
                    "changeset_id": str(changeset.id),
                    "summary": changeset.summary_en,
                },
            )

    return {"applied": True, "changeset_id": str(changeset.id), "summary": changeset.summary_en}


def undo_taxonomy_changeset(teacher_id: str, changeset_id: str) -> dict[str, Any]:
    """
    One-step Undo of a `TaxonomyChangeset`:
    Reverts all `MemoryCategoryLink` changes, restores previous category states,
    freezes affected categories for 30 days (`frozen_until`), and regenerates `CoreProfile`.
    """
    teacher = get_or_create_teacher(teacher_id)
    now = timezone.now()
    freeze_until = now + timedelta(days=UNDO_FREEZE_DAYS)

    with transaction.atomic():
        changeset = TaxonomyChangeset.objects.select_for_update().get(
            id=changeset_id,
            teacher=teacher,
        )
        if changeset.status == "reverted":
            return {"reverted": True, "changeset_id": str(changeset.id)}

        # Close all links opened by this changeset
        MemoryCategoryLink.objects.filter(changeset=changeset, valid_to__isnull=True).update(valid_to=now)

        for op in changeset.operations.all().order_by("-seq"):
            before = op.before_state
            after = op.after_state

            if op.op_type == "create_life_area":
                prev_map: dict[str, dict[str, Any]] = before.get("previous_categories", {})
                for mid, prev_cat_info in prev_map.items():
                    cat_obj = MemoryCategory.objects.filter(id=prev_cat_info["category_id"]).first()
                    sub_obj = (
                        MemoryCategory.objects.filter(id=prev_cat_info["subcategory_id"]).first()
                        if prev_cat_info.get("subcategory_id")
                        else None
                    )
                    if cat_obj:
                        cat_obj.frozen_until = freeze_until
                        cat_obj.save(update_fields=["frozen_until"])
                        MemoryCategoryLink.objects.create(
                            memory_id=mid,
                            category=cat_obj,
                            subcategory=sub_obj,
                            valid_from=now,
                        )
                created_la_id = after.get("created_life_area_id")
                if created_la_id:
                    MemoryCategory.objects.filter(id=created_la_id).update(
                        status="archived",
                        frozen_until=freeze_until,
                    )

            elif op.op_type == "archive_life_area" and op.target_category:
                cat = op.target_category
                cat.status = before.get("status", "active")
                cat.frozen_until = freeze_until
                cat.save(update_fields=["status", "frozen_until"])

            elif op.op_type == "merge_life_areas":
                src_id = before.get("source_category_id")
                src_cat = MemoryCategory.objects.filter(id=src_id).first()
                if src_cat:
                    src_cat.status = "active"
                    src_cat.merged_into = None
                    src_cat.frozen_until = freeze_until
                    src_cat.save(update_fields=["status", "merged_into", "frozen_until"])
                    for mid in before.get("memory_ids", []):
                        MemoryCategoryLink.objects.create(
                            memory_id=mid,
                            category=src_cat,
                            valid_from=now,
                        )
                if op.target_category:
                    op.target_category.frozen_until = freeze_until
                    op.target_category.save(update_fields=["frozen_until"])

            elif op.op_type == "refile":
                mid = before.get("memory_id")
                from_cat = MemoryCategory.objects.filter(id=before.get("from_category_id")).first()
                from_sub = (
                    MemoryCategory.objects.filter(id=before.get("from_subcategory_id")).first()
                    if before.get("from_subcategory_id")
                    else None
                )
                if from_cat and mid:
                    from_cat.frozen_until = freeze_until
                    from_cat.save(update_fields=["frozen_until"])
                    MemoryCategoryLink.objects.create(
                        memory_id=mid,
                        category=from_cat,
                        subcategory=from_sub,
                        valid_from=now,
                    )

            elif op.op_type == "split_subcategory":
                parent_cat = MemoryCategory.objects.filter(id=before.get("parent_category_id")).first()
                old_sub = MemoryCategory.objects.filter(id=before.get("old_subcategory_id")).first()
                if old_sub:
                    old_sub.status = "active"
                    old_sub.frozen_until = freeze_until
                    old_sub.save(update_fields=["status", "frozen_until"])
                if parent_cat:
                    parent_cat.frozen_until = freeze_until
                    parent_cat.save(update_fields=["frozen_until"])
                    for mid in before.get("memory_ids", []):
                        MemoryCategoryLink.objects.create(
                            memory_id=mid,
                            category=parent_cat,
                            subcategory=old_sub,
                            valid_from=now,
                        )
                for created_sub_id in after.get("created_subcategory_ids", []):
                    MemoryCategory.objects.filter(id=created_sub_id).update(status="archived")

            elif op.op_type == "create_subcategory":
                parent_cat = MemoryCategory.objects.filter(id=before.get("parent_category_id")).first()
                prev_subs: dict[str, str | None] = before.get("previous_subcategory_ids", {})
                if parent_cat:
                    parent_cat.frozen_until = freeze_until
                    parent_cat.save(update_fields=["frozen_until"])
                    for mid in before.get("memory_ids", []):
                        prev_sub_id = prev_subs.get(mid)
                        prev_sub = MemoryCategory.objects.filter(id=prev_sub_id).first() if prev_sub_id else None
                        MemoryCategoryLink.objects.create(
                            memory_id=mid,
                            category=parent_cat,
                            subcategory=prev_sub,
                            valid_from=now,
                        )
                created_sub_id = after.get("created_subcategory_id")
                if created_sub_id:
                    MemoryCategory.objects.filter(id=created_sub_id).update(status="archived")

        changeset.status = "reverted"
        changeset.reverted_at = now
        changeset.save(update_fields=["status", "reverted_at"])

        MemoryNotification.objects.filter(changeset=changeset).update(
            action="undone",
            seen_at=now,
        )

        regenerate_core_profile(teacher)

        MemoryEvent.objects.create(
            teacher=teacher,
            event="taxonomy.changeset_reverted",
            actor="teacher",
            payload={
                "changeset_id": str(changeset.id),
                "frozen_until": freeze_until.isoformat(),
            },
        )

    return {
        "reverted": True,
        "changeset_id": str(changeset.id),
        "frozen_until": freeze_until.isoformat(),
    }


# --- Teacher Manual Life Area Controls (PRD line 117: "Their changes always win over dreaming") ---


def teacher_manage_life_area(
    teacher_id: str,
    action: str,
    label_en: str = "",
    label_sw: str = "",
    category_id: str | None = None,
    target_category_id: str | None = None,
) -> dict[str, Any]:
    """
    Allow a teacher to create, rename, merge, restore, or delete a Life Area on the memory page.
    Sets `created_by='teacher'` so dreaming never overwrites teacher-defined names.
    """
    teacher = get_or_create_teacher(teacher_id)
    now = timezone.now()

    with transaction.atomic():
        if action == "create":
            active_count = MemoryCategory.objects.filter(
                teacher=teacher,
                kind="life_area",
                status="active",
            ).count()
            if active_count >= MAX_ACTIVE_LIFE_AREAS_PER_TEACHER:
                return {"ok": False, "reason": "max_active_life_areas_reached"}
            slug = re.sub(r"[^a-z0-9]+", "_", label_en.lower()).strip("_") or "custom_area"
            cat = MemoryCategory.objects.create(
                teacher=teacher,
                kind="life_area",
                slug=slug,
                label_en=label_en.strip(),
                label_sw=(label_sw or label_en).strip(),
                sensitivity="normal",
                is_protected=False,
                status="active",
                created_by="teacher",
                centroid=embed_text(f"{label_en} {label_sw}"),
                last_memory_at=now,
            )
            regenerate_core_profile(teacher)
            return {"ok": True, "action": "create", "category_id": str(cat.id), "label_en": cat.label_en}

        if not category_id:
            return {"ok": False, "reason": "category_id_required"}

        cat = MemoryCategory.objects.select_for_update().get(id=category_id, teacher=teacher, kind="life_area")

        if action == "rename":
            cat.label_en = label_en.strip()
            if label_sw:
                cat.label_sw = label_sw.strip()
            cat.created_by = "teacher"
            cat.last_renamed_at = now
            cat.save(update_fields=["label_en", "label_sw", "created_by", "last_renamed_at"])
            regenerate_core_profile(teacher)
            return {"ok": True, "action": "rename", "category_id": str(cat.id), "label_en": cat.label_en}

        if action == "restore":
            cat.status = "active"
            cat.last_memory_at = now
            cat.save(update_fields=["status", "last_memory_at"])
            regenerate_core_profile(teacher)
            return {"ok": True, "action": "restore", "category_id": str(cat.id)}

        if action == "merge" and target_category_id:
            target = MemoryCategory.objects.select_for_update().get(
                id=target_category_id,
                teacher=teacher,
                kind="life_area",
            )
            active_links = list(MemoryCategoryLink.objects.filter(category=cat, valid_to__isnull=True))
            MemoryCategoryLink.objects.filter(category=cat, valid_to__isnull=True).update(valid_to=now)
            for lnk in active_links:
                MemoryCategoryLink.objects.create(
                    memory=lnk.memory,
                    category=target,
                    valid_from=now,
                )
            cat.status = "merged"
            cat.merged_into = target
            cat.save(update_fields=["status", "merged_into"])
            update_category_centroid(target, teacher=teacher)
            regenerate_core_profile(teacher)
            return {"ok": True, "action": "merge", "merged_into_id": str(target.id)}

        if action == "delete":
            # Move any active memories in this life area back to Profile or hard-delete the life area
            profile_cat = MemoryCategory.objects.filter(teacher__isnull=True, slug="profile", kind="core").first()
            active_links = list(MemoryCategoryLink.objects.filter(category=cat, valid_to__isnull=True))
            MemoryCategoryLink.objects.filter(category=cat, valid_to__isnull=True).update(valid_to=now)
            if profile_cat:
                for lnk in active_links:
                    MemoryCategoryLink.objects.create(
                        memory=lnk.memory,
                        category=profile_cat,
                        valid_from=now,
                    )
            cat.delete()
            regenerate_core_profile(teacher)
            return {"ok": True, "action": "delete"}

    return {"ok": False, "reason": f"unknown_action:{action}"}


def check_global_promotion_candidates() -> list[dict[str, Any]]:
    """
    Promote rule (PRD line 112):
    When similar teacher-level categories exist for >= 200 teachers, propose in the admin
    (never automatic).
    """
    from django.db.models import Count
    counts = (
        MemoryCategory.objects.filter(kind__in=["life_area", "sub"], teacher__isnull=False, status="active")
        .values("slug", "label_en", "label_sw", "kind")
        .annotate(n_teachers=Count("teacher", distinct=True))
        .filter(n_teachers__gte=PROMOTE_GLOBAL_MIN_TEACHERS)
    )
    proposals: list[dict[str, Any]] = []
    for row in counts:
        cs, _ = TaxonomyChangeset.objects.get_or_create(
            teacher=None,
            source="global_promotion_detector",
            status="proposed",
            summary_en=f"Promote '{row['label_en']}' ({row['n_teachers']} teachers) to shared global taxonomy",
            defaults={"summary_sw": f"Pandisha '{row['label_sw']}' kwenye mtaala wa pamoja"},
        )
        proposals.append(
            {
                "changeset_id": str(cs.id),
                "slug": row["slug"],
                "label_en": row["label_en"],
                "n_teachers": row["n_teachers"],
                "status": cs.status,
            }
        )
    return proposals
