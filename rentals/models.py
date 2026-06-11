from decimal import Decimal
import secrets

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from catalog.models import Bike, PickupLocation, Tariff


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает подтверждения"
        CONFIRMED = "confirmed", "Подтвержден"
        CANCELLED = "cancelled", "Отменен"
        EXPIRED = "expired", "Неявка / истек"
        ACTIVE = "active", "Активная аренда"
        COMPLETED = "completed", "Завершен"

    number = models.CharField("Номер брони", max_length=20, unique=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings")
    bike = models.ForeignKey(Bike, on_delete=models.PROTECT, related_name="bookings")
    pickup_location = models.ForeignKey(PickupLocation, on_delete=models.PROTECT, related_name="bookings")
    tariff = models.ForeignKey(Tariff, on_delete=models.PROTECT, related_name="bookings")
    start_at = models.DateTimeField("Начало аренды")
    end_at = models.DateTimeField("Плановый возврат")
    comment = models.TextField("Комментарий клиента", blank=True)
    cancellation_reason = models.CharField("Причина отмены", max_length=255, blank=True)
    quoted_price = models.DecimalField("Предварительная стоимость", max_digits=10, decimal_places=2, default=0)
    deposit_amount = models.DecimalField("Залог", max_digits=10, decimal_places=2, default=0)
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Бронирование"
        verbose_name_plural = "Бронирования"

    def __str__(self):
        return f"{self.number} / {self.customer}"

    def duration_hours(self) -> Decimal:
        delta = self.end_at - self.start_at
        return Decimal(max(delta.total_seconds() / 3600, 1))


class Rental(models.Model):
    class Status(models.TextChoices):
        READY = "ready", "Подготовлена к выдаче"
        ACTIVE = "active", "Активна"
        COMPLETED = "completed", "Завершена"
        OVERDUE = "overdue", "Просрочена"
        CANCELLED = "cancelled", "Отменена"

    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="rental")
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="issued_rentals")
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="received_rentals")
    actual_start_at = models.DateTimeField("Фактическая выдача", null=True, blank=True)
    actual_end_at = models.DateTimeField("Фактический возврат", null=True, blank=True)
    start_condition = models.TextField("Состояние при выдаче", blank=True)
    end_condition = models.TextField("Состояние при возврате", blank=True)
    damage_fee = models.DecimalField("Штраф за повреждение", max_digits=10, decimal_places=2, default=0)
    late_fee = models.DecimalField("Штраф за просрочку", max_digits=10, decimal_places=2, default=0)
    extra_time_fee = models.DecimalField("Доплата за превышение времени", max_digits=10, decimal_places=2, default=0)
    final_price = models.DecimalField("Итоговая стоимость", max_digits=10, decimal_places=2, default=0)
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.READY)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Аренда"
        verbose_name_plural = "Аренды"

    def __str__(self):
        return f"Аренда {self.booking.number}"


class Payment(models.Model):
    class Kind(models.TextChoices):
        RENTAL = "rental", "Оплата аренды"
        DEPOSIT = "deposit", "Залог"
        REFUND = "refund", "Возврат залога"
        FINE = "fine", "Штраф"

    class Method(models.TextChoices):
        CASH = "cash", "Наличные"
        QR = "qr", "QR-код"
        CARD = "card", "Карта (архив)"
        ONLINE = "online", "Онлайн (архив)"

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает оплаты"
        PAID = "paid", "Оплачено"
        FAILED = "failed", "Ошибка"

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField("Сумма", max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    kind = models.CharField("Тип платежа", max_length=20, choices=Kind.choices)
    method = models.CharField("Метод оплаты", max_length=20, choices=Method.choices, default=Method.CASH)
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.PENDING)
    external_id = models.CharField("Внешний ID", max_length=120, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Платеж"
        verbose_name_plural = "Платежи"

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount}"


def make_booking_number() -> str:
    for _ in range(20):
        number = f"VR-{secrets.randbelow(10000):04d}"
        if not Booking.objects.filter(number=number).exists():
            return number
    return timezone.now().strftime("VR%H%M%S")
