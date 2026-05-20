from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AccountAccessCode, EmailVerificationCode, User, UserNotification


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Дополнительные данные", {"fields": ("phone", "telegram", "role", "email_verified_at")}),
        ("VK", {"fields": ("vk_id", "vk_screen_name", "vk_photo_url", "vk_notifications_enabled")}),
    )
    list_display = (
        "username",
        "staff_display",
        "email",
        "email_verified_at",
        "first_name",
        "last_name",
        "role",
        "vk_id",
        "vk_notifications_enabled",
        "is_staff",
    )
    list_filter = ("role", "vk_notifications_enabled", "email_verified_at", "is_staff", "is_superuser")


@admin.register(AccountAccessCode)
class AccountAccessCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "created_by_display", "created_at", "expires_at", "used_at", "attempts")
    list_filter = ("created_at", "expires_at", "used_at")
    search_fields = ("user__username", "user__phone")
    readonly_fields = ("user", "created_by", "code_hash", "expires_at", "used_at", "attempts", "created_at")

    @admin.display(description="Код выдал")
    def created_by_display(self, obj):
        return obj.created_by.staff_display if obj.created_by else "-"


@admin.register(EmailVerificationCode)
class EmailVerificationCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "email", "created_at", "expires_at", "used_at", "attempts")
    list_filter = ("created_at", "expires_at", "used_at")
    search_fields = ("user__username", "user__phone", "user__email", "email")
    readonly_fields = ("user", "email", "code_hash", "expires_at", "used_at", "attempts", "created_at")


@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "level", "created_at", "read_at")
    list_filter = ("level", "created_at", "read_at")
    search_fields = ("user__username", "user__phone", "user__email", "title", "message")
    readonly_fields = ("user", "title", "message", "url", "level", "created_at", "read_at")
