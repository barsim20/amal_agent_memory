"""Django admin registrations for Amal Memory models."""
from django.contrib import admin
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
    TaxonomyChangeset,
    TaxonomyOperation,
    TeacherProfile,
)

admin.site.register(TeacherProfile)
admin.site.register(MemoryCategory)
admin.site.register(MemoryItem)
admin.site.register(MemoryCategoryLink)
admin.site.register(TaxonomyChangeset)
admin.site.register(TaxonomyOperation)
admin.site.register(MemoryEvidence)
admin.site.register(MemoryEvent)
admin.site.register(MemoryTombstone)
admin.site.register(CoreProfile)
admin.site.register(AggregateInsight)
admin.site.register(MemorySettings)
admin.site.register(MemoryNotification)
admin.site.register(ConsentRequest)
