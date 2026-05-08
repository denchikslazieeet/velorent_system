from django.contrib import admin
from .models import Bike, BikeCategory, PickupLocation, Tariff

@admin.register(PickupLocation)
class PickupLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "phone", "is_active")
    list_filter = ("is_active",)

@admin.register(BikeCategory)
class BikeCategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)

@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ("name", "hourly_rate", "daily_rate", "deposit_amount", "late_fee_per_hour", "is_active")
    list_filter = ("is_active",)

@admin.register(Bike)
class BikeAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "current_location", "status", "serial_number")
    list_filter = ("status", "category", "current_location")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "serial_number")
