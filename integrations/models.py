from django.db import models
from django.utils import timezone


class EmailDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        SENT = "sent", "Отправлено"
        FAILED = "failed", "Ошибка"

    recipient = models.EmailField("Получатель")
    subject = models.CharField("Тема", max_length=255)
    body = models.TextField("Текст письма")
    kind = models.CharField("Тип письма", max_length=100, blank=True)
    deduplication_key = models.CharField(
        "Ключ защиты от дублей",
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    attempts = models.PositiveSmallIntegerField("Попыток", default=0)
    next_attempt_at = models.DateTimeField("Следующая попытка", default=timezone.now)
    sent_at = models.DateTimeField("Отправлено", null=True, blank=True)
    last_error = models.TextField("Последняя ошибка", blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Доставка письма"
        verbose_name_plural = "Доставка писем"

    def __str__(self):
        return f"{self.recipient}: {self.subject}"


class BookingNotificationEvent(models.Model):
    class Audience(models.TextChoices):
        CUSTOMER = "customer", "Клиент"
        OPERATOR = "operator", "Оператор"

    booking = models.ForeignKey(
        "rentals.Booking",
        on_delete=models.CASCADE,
        related_name="notification_events",
        verbose_name="Бронь",
    )
    event = models.CharField("Событие", max_length=100)
    audience = models.CharField("Получатель", max_length=20, choices=Audience.choices)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "event", "audience"],
                name="unique_booking_notification_event",
            ),
        ]
        verbose_name = "Событие уведомления по брони"
        verbose_name_plural = "События уведомлений по броням"

    def __str__(self):
        return f"{self.booking.number}: {self.event} / {self.audience}"


class SyncEvent(models.Model):
    class Direction(models.TextChoices):
        TO_ONEC = "to_1c", "В 1С"
        FROM_ONEC = "from_1c", "Из 1С"

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        SENT = "sent", "Отправлено"
        FAILED = "failed", "Ошибка"

    entity = models.CharField("Сущность", max_length=100)
    entity_id = models.CharField("Идентификатор сущности", max_length=100)
    event_type = models.CharField("Тип события", max_length=100)
    payload = models.JSONField("Данные")
    direction = models.CharField("Направление", max_length=20, choices=Direction.choices)
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.PENDING)
    response_text = models.TextField("Ответ системы", blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Событие синхронизации"
        verbose_name_plural = "События синхронизации"

    def __str__(self):
        return f"{self.entity}:{self.entity_id} ({self.event_type})"
