from django.conf import settings
from django.core.management.base import BaseCommand

from catalog.models import PickupLocation


class Command(BaseCommand):
    help = "Обновляет публичный адрес и контакты основной точки выдачи."

    def handle(self, *args, **options):
        location = PickupLocation.objects.filter(is_active=True).order_by("id").first()
        if location is None:
            location = PickupLocation(name="ВелоРент - Бутина 50", is_active=True)

        location.address = settings.RENTAL_PROVIDER_ADDRESS
        location.phone = settings.RENTAL_PROVIDER_PHONE
        location.map_url = ""
        location.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Основная точка выдачи обновлена: {location.address}, {location.phone}. "
                f"Режим работы сохранён: {location.opening_hours or 'не указан'}."
            )
        )
