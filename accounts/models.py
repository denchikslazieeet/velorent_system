from datetime import timedelta
import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Клиент"
        OPERATOR = "operator", "Оператор"
        ADMIN = "admin", "Администратор"

    class DocumentType(models.TextChoices):
        PASSPORT = "passport", "Паспорт РФ"
        FOREIGN_PASSPORT = "foreign_passport", "Загранпаспорт"
        DRIVER_LICENSE = "driver_license", "Водительское удостоверение"
        OTHER = "other", "Иной документ"

    phone = models.CharField("Телефон", max_length=20, blank=True)
    role = models.CharField("Роль", max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    telegram = models.CharField("Telegram", max_length=64, blank=True)
    vk_id = models.CharField("VK ID", max_length=32, unique=True, null=True, blank=True)
    vk_screen_name = models.CharField("VK короткое имя", max_length=120, blank=True)
    vk_photo_url = models.URLField("VK фото", blank=True)
    vk_notifications_enabled = models.BooleanField("Уведомления VK включены", default=True)

    next_booking_hourly_surcharge = models.DecimalField(
        "Надбавка на следующее бронирование (₽/час)",
        max_digits=10,
        decimal_places=2,
        default=0
    )
    next_booking_penalty_reason = models.CharField(
        "Причина надбавки",
        max_length=255,
        blank=True
    )

    terms_accepted = models.BooleanField("Условия аренды приняты", default=False)
    terms_accepted_at = models.DateTimeField("Дата принятия условий", null=True, blank=True)
    personal_data_consent = models.BooleanField("Согласие на обработку ПД", default=False)
    personal_data_consent_at = models.DateTimeField("Дата согласия на обработку ПД", null=True, blank=True)

    document_verified = models.BooleanField("Документ проверен оператором", default=False)
    document_type = models.CharField(
        "Тип документа",
        max_length=30,
        choices=DocumentType.choices,
        blank=True
    )
    document_last4 = models.CharField("Последние 4 цифры документа", max_length=4, blank=True)
    document_verified_at = models.DateTimeField("Дата проверки документа", null=True, blank=True)
    document_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_customers",
        verbose_name="Проверил оператор"
    )

    def __str__(self):
        return self.get_full_name() or self.phone or self.username

    @property
    def full_name_or_phone(self):
        full_name = self.get_full_name().strip()
        return full_name or self.phone

    @property
    def display_name(self):
        return self.get_full_name().strip() or self.username or self.phone

    @property
    def staff_display(self):
        role_label = self.get_role_display()
        return f"{role_label} {self.display_name}".strip()

    def mark_consents_accepted(self):
        now = timezone.now()
        self.terms_accepted = True
        self.personal_data_consent = True
        self.terms_accepted_at = now
        self.personal_data_consent_at = now


class AccountAccessCode(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="account_access_codes",
        verbose_name="Пользователь",
    )
    code_hash = models.CharField("Hash кода", max_length=128)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_account_access_codes",
        verbose_name="Код выдал",
    )
    expires_at = models.DateTimeField("Действует до")
    used_at = models.DateTimeField("Использован", null=True, blank=True)
    attempts = models.PositiveSmallIntegerField("Попытки", default=0)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Код доступа к аккаунту"
        verbose_name_plural = "Коды доступа к аккаунтам"

    def __str__(self):
        return f"{self.user} / {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def is_active(self):
        return (
            self.used_at is None
            and self.expires_at >= timezone.now()
            and self.attempts < settings.ACCOUNT_ACCESS_CODE_MAX_ATTEMPTS
        )

    def check_code(self, raw_code):
        return check_password(raw_code, self.code_hash)

    def mark_used(self):
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])

    @classmethod
    def create_for_user(cls, user, created_by=None):
        now = timezone.now()
        cls.objects.filter(user=user, used_at__isnull=True).update(used_at=now)

        raw_code = f"{secrets.randbelow(1000000):06d}"
        access_code = cls.objects.create(
            user=user,
            code_hash=make_password(raw_code),
            created_by=created_by,
            expires_at=now + timedelta(minutes=settings.ACCOUNT_ACCESS_CODE_TTL_MINUTES),
        )
        return access_code, raw_code
