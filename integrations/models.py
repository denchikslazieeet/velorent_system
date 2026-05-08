from django.db import models

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
