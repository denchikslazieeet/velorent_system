from django.core.management.base import BaseCommand

from integrations.services import queue_booking_sync
from integrations.vk_notifications import notify_booking_event
from rentals.services import expire_stale_bookings


class Command(BaseCommand):
    help = "Закрывает прошедшие невыданные брони и освобождает велосипеды."

    def handle(self, *args, **options):
        expired = expire_stale_bookings()
        for booking in expired:
            queue_booking_sync(booking)
            notify_booking_event(booking, "expired")

        self.stdout.write(
            self.style.SUCCESS(f"Истекших броней закрыто: {len(expired)}.")
        )
