"""URL routes for Amal Memory Web UI and REST APIs."""
from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard_view, name="memory_dashboard"),
    path("memory/", views.dashboard_view, name="memory_page"),
    path("api/memories/", views.api_memories, name="api_memories"),
    path("api/memories/delete-all/", views.api_delete_all, name="api_delete_all"),
    path("api/memories/export/", views.api_export_memories, name="api_export_memories"),
    path("api/memories/<str:memory_id>/", views.api_memory_detail, name="api_memory_detail"),
    path("api/consent/<str:consent_id>/", views.api_resolve_consent, name="api_resolve_consent"),
    path("api/notifications/<str:notification_id>/action/", views.api_notification_action, name="api_notification_action"),
    path("api/live-pass/", views.api_live_pass, name="api_live_pass"),
    path("api/dream/", views.api_dream_run, name="api_dream_run"),
    path("api/retrieve/", views.api_retrieve_context, name="api_retrieve_context"),
    path("api/taxonomy/undo/<str:changeset_id>/", views.api_taxonomy_undo, name="api_taxonomy_undo"),
    path("api/taxonomy/apply/<str:changeset_id>/", views.api_taxonomy_apply, name="api_taxonomy_apply"),
    path("api/life-areas/", views.api_life_areas, name="api_life_areas"),
    path("api/settings/", views.api_settings, name="api_settings"),
    path("api/seed-demo/", views.api_seed_demo, name="api_seed_demo"),
    path("api/admin/inspect/", views.api_admin_inspect, name="api_admin_inspect"),
]
