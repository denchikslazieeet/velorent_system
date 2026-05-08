from django.contrib import admin
from .models import SyncEvent

@admin.register(SyncEvent)
class SyncEventAdmin(admin.ModelAdmin):
    list_display = ("entity", "entity_id", "event_type", "direction", "status", "created_at")
    list_filter = ("direction", "status", "event_type")
