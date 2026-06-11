from django.contrib import admin
from .models import BookingNotificationEvent, EmailDelivery, SyncEvent


@admin.register(EmailDelivery)
class EmailDeliveryAdmin(admin.ModelAdmin):
    list_display = ("recipient", "subject", "kind", "status", "attempts", "created_at")
    list_filter = ("status", "kind")
    search_fields = ("recipient", "subject", "body", "last_error")
    readonly_fields = ("created_at", "updated_at", "sent_at")


@admin.register(BookingNotificationEvent)
class BookingNotificationEventAdmin(admin.ModelAdmin):
    list_display = ("booking", "event", "audience", "created_at")
    list_filter = ("event", "audience")
    search_fields = ("booking__number",)
    readonly_fields = ("created_at",)

@admin.register(SyncEvent)
class SyncEventAdmin(admin.ModelAdmin):
    list_display = ("entity", "entity_id", "event_type", "direction", "status", "created_at")
    list_filter = ("direction", "status", "event_type")
    search_fields = ("entity", "entity_id", "event_type", "payload", "response_text")
    readonly_fields = ("created_at",)
