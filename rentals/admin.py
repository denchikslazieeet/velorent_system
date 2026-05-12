from django.contrib import admin
from .models import Booking, Rental, Payment

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("number", "customer", "bike", "start_at", "end_at", "status", "quoted_price")
    list_filter = ("status", "pickup_location")
    search_fields = (
        "number",
        "customer__username",
        "customer__phone",
        "customer__email",
        "bike__title",
        "comment",
        "cancellation_reason",
    )

@admin.register(Rental)
class RentalAdmin(admin.ModelAdmin):
    list_display = ("booking", "status", "actual_start_at", "actual_end_at", "final_price")
    list_filter = ("status",)

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("booking", "kind", "method", "amount", "status", "created_at")
    list_filter = ("kind", "method", "status")
