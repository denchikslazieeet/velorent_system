from django.contrib import admin
from django.utils.html import format_html

from .models import Bike, BikeCategory, PickupLocation, Tariff

@admin.register(PickupLocation)
class PickupLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "phone", "latitude", "longitude", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "address", "phone")
    list_editable = ("is_active",)

@admin.register(BikeCategory)
class BikeCategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name", "description")

@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ("name", "hourly_rate", "daily_rate", "deposit_amount", "late_fee_per_hour", "is_active")
    list_filter = ("is_active",)
    list_editable = ("is_active",)
    search_fields = ("name",)

@admin.register(Bike)
class BikeAdmin(admin.ModelAdmin):
    list_display = ("photo_thumb", "title", "category", "current_location", "status", "tariff", "serial_number")
    list_filter = ("status", "category", "current_location")
    list_select_related = ("category", "current_location", "tariff")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "serial_number", "color", "category__name")
    readonly_fields = ("photo_preview",)

    @admin.display(description="Фото")
    def photo_thumb(self, obj):
        if not obj.photo:
            return "—"
        return format_html(
            '<img src="{}" style="width: 76px; height: 52px; object-fit: cover; border-radius: 8px;" alt="">',
            obj.photo.url,
        )

    @admin.display(description="Текущее фото")
    def photo_preview(self, obj):
        if not obj.photo:
            return "Фото пока не загружено."
        return format_html(
            '<img src="{}" style="width: min(520px, 100%); max-height: 320px; object-fit: contain; border-radius: 14px; background: #0b1220; padding: 12px;" alt="">',
            obj.photo.url,
        )
