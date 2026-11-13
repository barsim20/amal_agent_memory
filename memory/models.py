"""Relational data models for Amal Memory and Dreaming (Postgres/pgvector + SQLite compatible)."""
from __future__ import annotations

import uuid
from datetime import timedelta
from django.db import models
from django.utils import timezone

from .constants import CONSENT_EXPIRY_DAYS


class TeacherProfile(models.Model):
    """Unified teacher identity across WhatsApp and Amal Web."""

    teacher_id = models.CharField(max_length=64, primary_key=True)
    display_name = models.CharField(max_length=128, blank=True, default="")
    phone_hash = models.CharField(max_length=128, blank=True, default="")
    country = models.CharField(max_length=32, default="KE")  # KE (Kenya) or RW (Rwanda)
    cohort_key = models.CharField(max_length=128, default="kisumu-cohort-1")
    curriculum = models.CharField(max_length=64, default="CBC")
    preferred_lang = models.CharField(max_length=16, default="en")
    last_active_at = models.DateTimeField(default=timezone.now)
    last_dreamed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["teacher_id"]

    def __str__(self) -> str:
        return f"{self.display_name or self.teacher_id} ({self.country})"


class MemoryCategory(models.Model):
    """
    Three-layer taxonomy node:
    - 'core': 10 protected top-level categories (teacher=None for global definitions)
    - 'life_area': dynamic per-teacher top-level categories (capped at 8 active)
    - 'sub': subcategories under either core categories or life areas
    """

    KIND_CHOICES = [
        ("core", "Core Category (Protected)"),
        ("life_area", "Life Area (Dynamic Top-Level)"),
        ("sub", "Subcategory"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("archived", "Archived"),
        ("merged", "Merged"),
        ("proposed_global", "Proposed Global"),
    ]
    SENSITIVITY_CHOICES = [
        ("normal", "Normal"),
        ("consent", "Consent Required"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="categories",
        help_text="Null for global core categories/subcategories; set for teacher-specific categories.",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    path = models.CharField(
        max_length=512,
        db_index=True,
        blank=True,
        default="",
        help_text="Materialized ltree-compatible path built from stable category slugs/ids.",
    )
    slug = models.CharField(max_length=128, db_index=True)
    label_en = models.CharField(max_length=128)
    label_sw = models.CharField(max_length=128, blank=True, default="")
    kind = models.CharField(max_length=24, choices=KIND_CHOICES, default="core")
    sensitivity = models.CharField(max_length=16, choices=SENSITIVITY_CHOICES, default="normal")
    is_protected = models.BooleanField(default=False)
    global_ref = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teacher_instances",
    )
    centroid = models.JSONField(
        null=True,
        blank=True,
        help_text="1024-dim halfvec centroid for category similarity & re-filing.",
    )
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="active", db_index=True)
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_sources",
    )
    created_by = models.CharField(
        max_length=32,
        default="system",
        help_text="'system', 'dreaming', 'teacher', or 'admin'",
    )
    last_renamed_at = models.DateTimeField(null=True, blank=True)
    last_split_at = models.DateTimeField(null=True, blank=True)
    frozen_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set for 30 days when a teacher undoes a taxonomy change on this category.",
    )
    last_memory_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["teacher", "kind", "status"]),
            models.Index(fields=["slug", "kind"]),
        ]

    def save(self, *args, **kwargs):
        node_token = self.slug.replace("-", "_")
        if self.parent_id and self.parent:
            parent_path = self.parent.path or self.parent.slug.replace("-", "_")
            self.path = f"{parent_path}.{node_token}"
        else:
            self.path = node_token
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.label_en} ({self.kind})"


class MemoryItem(models.Model):
    """
    Atomic, bi-temporal teacher memory row.
    Never updated in-place for content corrections; superseded by a new row instead.
    Hard-deleted immediately when the teacher deletes or revokes consent.
    """

    SCOPE_CHOICES = [
        ("teacher", "Teacher"),
        ("cohort", "Cohort / School"),
        ("global", "Global"),
    ]
    LANG_CHOICES = [
        ("en", "English"),
        ("sw", "Kiswahili"),
        ("mixed", "Code-switched (EN/SW)"),
    ]
    SOURCE_CHOICES = [
        ("stated", "Stated by teacher"),
        ("observed", "Observed from product usage"),
    ]
    SENSITIVITY_CHOICES = [
        ("normal", "Normal"),
        ("consent", "Consent Required"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("pending_consent", "Pending Consent"),
        ("superseded", "Superseded"),
        ("archived", "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="memories",
        db_index=True,
    )
    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES, default="teacher")
    statement = models.TextField(help_text="Short, atomic statement.")
    slot = models.CharField(
        max_length=128,
        db_index=True,
        default="general",
        help_text="Semantic slot key (e.g., 'teaching_context.class_size') used for contradiction/supersession and tombstones.",
    )
    learner_pseudonym_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Pseudonymous ID when category is named_learners.",
    )
    lang = models.CharField(max_length=12, choices=LANG_CHOICES, default="en")
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default="stated")
    sensitivity = models.CharField(max_length=16, choices=SENSITIVITY_CHOICES, default="normal")
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="active", db_index=True)
    confidence = models.FloatField(default=0.95)
    salience = models.FloatField(default=0.80)
    embedding = models.JSONField(
        default=list,
        help_text="1024-dim halfvec representation stored as float array (and pgvector halfvec(1024) on Postgres).",
    )
    embed_model = models.CharField(max_length=64, default="AfriE5-Large-Instruct-halfvec1024")
    tsv_tokens = models.TextField(
        blank=True,
        default="",
        help_text="Normalized lowercase tokens using 'simple' (un-stemmed) tokenization for EN + Kiswahili FTS.",
    )

    # Bi-temporal columns (world time: valid_from/valid_to; system transaction time: recorded_at/retired_at)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField(null=True, blank=True)
    recorded_at = models.DateTimeField(default=timezone.now)
    retired_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supersedes",
    )
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=32, default="live_pass")

    class Meta:
        indexes = [
            models.Index(fields=["teacher", "status"]),
            models.Index(fields=["teacher", "slot", "status"]),
        ]
        ordering = ["-recorded_at"]

    def __str__(self) -> str:
        return f"[{self.status}] {self.statement[:60]}"


class TaxonomyChangeset(models.Model):
    """
    A versioned nightly or manual reorganization containing ordered TaxonomyOperations.
    Can be reverted in one step.
    """

    STATUS_CHOICES = [
        ("proposed", "Proposed"),
        ("applied", "Applied"),
        ("reverted", "Reverted"),
        ("rejected", "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="taxonomy_changesets",
    )
    source = models.CharField(max_length=32, default="dreaming")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="proposed", db_index=True)
    summary_en = models.CharField(max_length=255, blank=True, default="")
    summary_sw = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    reverted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Changeset {self.id} ({self.status}): {self.summary_en}"


class TaxonomyOperation(models.Model):
    """Ordered atomic operation inside a TaxonomyChangeset."""

    OP_CHOICES = [
        ("create_life_area", "Create Life Area"),
        ("archive_life_area", "Archive Life Area"),
        ("merge_life_areas", "Merge Life Areas"),
        ("refile", "Re-file Memory"),
        ("split_subcategory", "Split Subcategory"),
        ("merge_subcategory", "Merge Subcategory"),
        ("create_subcategory", "Create Subcategory"),
        ("rename", "Rename Category"),
        ("promote", "Promote to Global Taxonomy"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    changeset = models.ForeignKey(
        TaxonomyChangeset,
        on_delete=models.CASCADE,
        related_name="operations",
    )
    seq = models.PositiveIntegerField(default=0)
    op_type = models.CharField(max_length=32, choices=OP_CHOICES)
    target_category = models.ForeignKey(
        MemoryCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operations",
    )
    before_state = models.JSONField(default=dict)
    after_state = models.JSONField(default=dict)

    class Meta:
        ordering = ["seq"]


class MemoryCategoryLink(models.Model):
    """
    Temporal assignment linking a MemoryItem to a top-level category and optional subcategory.
    Reorganizations close old links (valid_to) and open new links without mutating MemoryItem rows.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    memory = models.ForeignKey(
        MemoryItem,
        on_delete=models.CASCADE,
        related_name="category_links",
    )
    category = models.ForeignKey(
        MemoryCategory,
        on_delete=models.CASCADE,
        related_name="memory_links",
    )
    subcategory = models.ForeignKey(
        MemoryCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subcategory_memory_links",
    )
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField(null=True, blank=True, db_index=True)
    changeset = models.ForeignKey(
        TaxonomyChangeset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="category_links",
    )

    class Meta:
        indexes = [
            models.Index(fields=["memory", "valid_to"]),
            models.Index(fields=["category", "valid_to"]),
        ]


class MemoryEvidence(models.Model):
    """Provenance pointer to the message that produced a memory (stores no raw sensitive payload after deletion)."""

    SURFACE_CHOICES = [
        ("whatsapp", "WhatsApp"),
        ("web", "Amal Web"),
    ]
    AREA_CHOICES = [
        ("chat", "Assistant Chat"),
        ("academy", "Amal Academy"),
        ("tools", "Amal Tools"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    memory = models.ForeignKey(
        MemoryItem,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    surface = models.CharField(max_length=16, choices=SURFACE_CHOICES, default="whatsapp")
    product_area = models.CharField(max_length=16, choices=AREA_CHOICES, default="chat")
    conversation_id = models.CharField(max_length=128, db_index=True, default="conv-default")
    message_id = models.CharField(max_length=128, default="msg-1")
    quote_span = models.CharField(max_length=128, blank=True, default="0:0")
    extracted_by = models.CharField(max_length=64, default="memory_live_graph")
    created_at = models.DateTimeField(auto_now_add=True)


class MemoryEvent(models.Model):
    """
    Append-only audit and notification feed.
    Holds no deleted content after erasure.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="memory_events",
    )
    memory_id_ref = models.CharField(max_length=64, blank=True, default="")
    event = models.CharField(
        max_length=64,
        db_index=True,
        help_text="e.g., memory.saved, memory.updated, memory.deleted, memory.consent_requested, admin.inspected",
    )
    actor = models.CharField(max_length=64, default="system")
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class MemoryTombstone(models.Model):
    """
    Stores ONLY a keyed HMAC of the normalized statement and its category slot.
    Never stores raw text or embeddings. Blocks exact re-creation and flags same-slot near matches.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="tombstones",
    )
    statement_hmac = models.CharField(max_length=128, db_index=True)
    slot = models.CharField(max_length=128, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("teacher", "statement_hmac")]
        indexes = [
            models.Index(fields=["teacher", "slot"]),
        ]


class CoreProfile(models.Model):
    """
    Compact (~300 tokens max) always-injected profile summary built from
    Profile, Teaching context, Preferences, and active Life Areas.
    Regenerated nightly or immediately when a source memory in `built_from` is deleted/edited.
    """

    teacher = models.OneToOneField(
        TeacherProfile,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="core_profile",
    )
    summary = models.TextField(blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    built_from = models.JSONField(
        default=list,
        help_text="List of MemoryItem UUID strings used to build this profile.",
    )
    updated_at = models.DateTimeField(auto_now=True)


class AggregateInsight(models.Model):
    """
    Privacy-preserving cohort/school (n >= 10) and global (n >= 50) insights.
    Never contains teacher names or Named Learner memories.
    """

    SCOPE_CHOICES = [
        ("cohort", "Cohort / School (min 10 teachers)"),
        ("global", "Global (min 50 teachers)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES, db_index=True)
    scope_key = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Cohort ID or country/curriculum/lang key (e.g., 'KE:CBC:en').",
    )
    category = models.ForeignKey(
        MemoryCategory,
        on_delete=models.CASCADE,
        related_name="aggregate_insights",
    )
    statement = models.TextField()
    n_teachers = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["scope", "scope_key"]),
        ]


class MemorySettings(models.Model):
    """Teacher-owned memory controls and consent preferences."""

    SENSITIVE_MODE_CHOICES = [
        ("always_ask", "Always ask me before saving personal/sensitive memories"),
        ("never_remember", "Never remember personal or sensitive things"),
    ]
    BANNER_MODE_CHOICES = [
        ("realtime", "Show banner during web sessions (default)"),
        ("next_visit_summary", "Summary on next visit only"),
    ]

    teacher = models.OneToOneField(
        TeacherProfile,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="settings",
    )
    enabled = models.BooleanField(default=True)
    share_aggregate = models.BooleanField(default=True)
    sensitive_mode = models.CharField(
        max_length=24,
        choices=SENSITIVE_MODE_CHOICES,
        default="always_ask",
    )
    banner_mode = models.CharField(
        max_length=24,
        choices=BANNER_MODE_CHOICES,
        default="realtime",
    )
    whatsapp_onboarded = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


class MemoryNotification(models.Model):
    """
    Web notification feed & banner state for every saved/updated memory,
    pending consent item, or nightly taxonomy reorganization.
    """

    KIND_CHOICES = [
        ("saved", "Memory Saved"),
        ("updated", "Memory Updated"),
        ("consent_prompt", "Sensitive Memory Consent Card"),
        ("taxonomy_change", "Nightly Taxonomy Reorganization"),
    ]
    ACTION_CHOICES = [
        ("pending", "Pending / Unactioned"),
        ("kept", "Kept"),
        ("edited", "Edited"),
        ("undone", "Undone"),
        ("removed", "Removed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    memory = models.ForeignKey(
        MemoryItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    changeset = models.ForeignKey(
        TaxonomyChangeset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    category_slug = models.CharField(max_length=128, blank=True, default="")
    kind = models.CharField(max_length=24, choices=KIND_CHOICES, default="saved")
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")
    diff_before = models.TextField(blank=True, default="")
    diff_after = models.TextField(blank=True, default="")
    origin_surface = models.CharField(max_length=16, default="web")
    grouped_count = models.PositiveIntegerField(default=1)
    grouped_items = models.JSONField(default=list)
    seen_at = models.DateTimeField(null=True, blank=True)
    action = models.CharField(max_length=16, choices=ACTION_CHOICES, default="pending")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]


def _default_consent_expiry():
    return timezone.now() + timedelta(days=CONSENT_EXPIRY_DAYS)


class ConsentRequest(models.Model):
    """
    Tracks a sensitive candidate memory in the `pending_consent` queue.
    YES promotes the memory to `active`; NO or 7-day expiry hard-deletes it and records a tombstone
    so the agent never asks twice about the same item.
    """

    ANSWER_CHOICES = [
        ("pending", "Pending"),
        ("yes", "Yes (Consented)"),
        ("no", "No (Declined)"),
        ("expired", "Expired (7 days)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="consent_requests",
    )
    memory = models.OneToOneField(
        MemoryItem,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="consent_request",
    )
    statement_hmac = models.CharField(max_length=128, db_index=True)
    slot = models.CharField(max_length=128)
    prompt_text = models.TextField()
    asked_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(default=_default_consent_expiry)
    channel = models.CharField(max_length=16, default="whatsapp")
    answer = models.CharField(max_length=16, choices=ANSWER_CHOICES, default="pending", db_index=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-asked_at"]
