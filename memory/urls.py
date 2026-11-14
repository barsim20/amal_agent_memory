"""URL routes for Amal Memory Web UI and REST APIs (supports both with and without trailing slash for Next.js proxy)."""
from django.urls import re_path
from . import views

urlpatterns = [
    re_path(r"^$", views.dashboard_view, name="memory_dashboard"),
    re_path(r"^memory/?$", views.dashboard_view, name="memory_page"),
    re_path(r"^api/memories/?$", views.api_memories, name="api_memories"),
    re_path(r"^api/memories/import/?$", views.api_import_memories, name="api_import_memories"),
    re_path(r"^api/memories/delete-all/?$", views.api_delete_all, name="api_delete_all"),
    re_path(r"^api/memories/export/?$", views.api_export_memories, name="api_export_memories"),
    re_path(r"^api/download/zip/?$", views.api_download_repo_zip, name="api_download_repo_zip"),
    re_path(r"^api/download/bundle/?$", views.api_download_git_bundle, name="api_download_git_bundle"),
    re_path(r"^api/memories/(?P<memory_id>[^/]+)/?$", views.api_memory_detail, name="api_memory_detail"),
    re_path(r"^api/consent/(?P<consent_id>[^/]+)/?$", views.api_resolve_consent, name="api_resolve_consent"),
    re_path(r"^api/notifications/(?P<notification_id>[^/]+)/action/?$", views.api_notification_action, name="api_notification_action"),
    re_path(r"^api/chat/?$", views.api_chat, name="api_chat"),
    re_path(r"^api/memory-decision/?$", views.api_memory_decision, name="api_memory_decision"),
    re_path(r"^api/live-pass/?$", views.api_live_pass, name="api_live_pass"),
    re_path(r"^api/dream/?$", views.api_dream_run, name="api_dream_run"),
    re_path(r"^api/retrieve/?$", views.api_retrieve_context, name="api_retrieve_context"),
    re_path(r"^api/taxonomy/undo/(?P<changeset_id>[^/]+)/?$", views.api_taxonomy_undo, name="api_taxonomy_undo"),
    re_path(r"^api/taxonomy/apply/(?P<changeset_id>[^/]+)/?$", views.api_taxonomy_apply, name="api_taxonomy_apply"),
    re_path(r"^api/life-areas/?$", views.api_life_areas, name="api_life_areas"),
    re_path(r"^api/categories/(?P<category_id>[^/]+)/clear/?$", views.api_clear_category, name="api_clear_category"),
    re_path(r"^api/settings/?$", views.api_settings, name="api_settings"),
    re_path(r"^api/seed-demo/?$", views.api_seed_demo, name="api_seed_demo"),
    re_path(r"^api/admin/inspect/?$", views.api_admin_inspect, name="api_admin_inspect"),
]
