from urllib.parse import quote_plus

from django.db import models

class PickupLocation(models.Model):
    name = models.CharField("Название точки", max_length=120)
    address = models.CharField("Адрес", max_length=255)
    phone = models.CharField("Телефон", max_length=20, blank=True)
    opening_hours = models.CharField("Часы работы", max_length=120, blank=True)
    latitude = models.DecimalField("Широта", max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField("Долгота", max_digits=9, decimal_places=6, null=True, blank=True)
    map_url = models.URLField("Ссылка на карту", blank=True)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Точка выдачи"
        verbose_name_plural = "Точки выдачи"

    def __str__(self):
        return self.name

    @property
    def map_query(self):
        return self.address or self.name

    @property
    def map_search_url(self):
        if self.map_url:
            return self.map_url
        if self.latitude and self.longitude:
            return f"https://yandex.ru/maps/?ll={self.longitude}%2C{self.latitude}&z=16&pt={self.longitude},{self.latitude},pm2rdm"
        return f"https://yandex.ru/maps/?text={quote_plus(self.map_query)}"

    @property
    def route_url(self):
        if self.latitude and self.longitude:
            return f"https://yandex.ru/maps/?rtext=~{self.latitude}%2C{self.longitude}&rtt=auto"
        return self.map_search_url

    @property
    def map_embed_url(self):
        if self.latitude and self.longitude:
            return f"https://yandex.ru/map-widget/v1/?ll={self.longitude}%2C{self.latitude}&z=16&pt={self.longitude},{self.latitude},pm2rdm"
        return f"https://yandex.ru/map-widget/v1/?text={quote_plus(self.map_query)}"

class BikeCategory(models.Model):
    name = models.CharField("Категория", max_length=100)
    description = models.TextField("Описание", blank=True)

    class Meta:
        verbose_name = "Категория велосипеда"
        verbose_name_plural = "Категории велосипедов"

    def __str__(self):
        return self.name

class Tariff(models.Model):
    name = models.CharField("Название тарифа", max_length=120)
    hourly_rate = models.DecimalField("Цена за час", max_digits=10, decimal_places=2)
    daily_rate = models.DecimalField("Цена за сутки", max_digits=10, decimal_places=2, default=0)
    deposit_amount = models.DecimalField("Залог", max_digits=10, decimal_places=2, default=0)
    late_fee_per_hour = models.DecimalField("Штраф за час просрочки", max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Тариф"
        verbose_name_plural = "Тарифы"

    def __str__(self):
        return self.name

class Bike(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Доступен"
        RESERVED = "reserved", "Забронирован"
        IN_RENT = "in_rent", "В аренде"
        SERVICE = "service", "На обслуживании"
        RETIRED = "retired", "Списан"

    title = models.CharField("Название", max_length=150)
    slug = models.SlugField(unique=True)
    category = models.ForeignKey(BikeCategory, on_delete=models.PROTECT, related_name="bikes")
    tariff = models.ForeignKey(Tariff, on_delete=models.PROTECT, related_name="bikes")
    current_location = models.ForeignKey(PickupLocation, on_delete=models.PROTECT, related_name="bikes")
    serial_number = models.CharField("Серийный номер", max_length=120, unique=True)
    frame_size = models.CharField("Размер рамы", max_length=50, blank=True)
    wheel_size = models.CharField("Диаметр колеса", max_length=50, blank=True)
    color = models.CharField("Цвет", max_length=50, blank=True)
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    condition_notes = models.TextField("Комментарий по состоянию", blank=True)
    photo = models.ImageField("Фото", upload_to="bikes/", blank=True, null=True)
    description = models.TextField("Описание", blank=True)

    class Meta:
        verbose_name = "Велосипед"
        verbose_name_plural = "Велосипеды"

    def __str__(self):
        return self.title
