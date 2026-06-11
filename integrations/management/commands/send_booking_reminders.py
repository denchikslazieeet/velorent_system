from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from integrations.models import BookingNotificationEvent
from integrations.vk_notifications import notify_booking_event_once
from rentals.models import Booking


class Command(BaseCommand):
    help = "Отправляет одноразовые напоминания о выдаче, возврате и просрочке."

    def handle(self, *args, **options):
        now = timezone.now()
        sent = 0

        pickup_bookings = Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            start_at__gt=now,
            start_at__lte=now + timedelta(hours=settings.BOOKING_PICKUP_REMINDER_HOURS),
        ).select_related("customer", "bike", "pickup_location")
        for booking in pickup_bookings.iterator():
            if notify_booking_event_once(
                booking,
                "pickup_reminder",
                BookingNotificationEvent.Audience.CUSTOMER,
                deduplication_event=f"pickup_reminder:{booking.start_at.isoformat()}",
            ):
                sent += 1

        return_bookings = Booking.objects.filter(
            status=Booking.Status.ACTIVE,
            end_at__gt=now,
            end_at__lte=now + timedelta(hours=settings.BOOKING_RETURN_REMINDER_HOURS),
        ).select_related("customer", "bike", "pickup_location")
        for booking in return_bookings.iterator():
            if notify_booking_event_once(
                booking,
                "return_reminder",
                BookingNotificationEvent.Audience.CUSTOMER,
                deduplication_event=f"return_reminder:{booking.end_at.isoformat()}",
            ):
                sent += 1

        overdue_bookings = Booking.objects.filter(
            status=Booking.Status.ACTIVE,
            end_at__lte=now - timedelta(
                minutes=settings.BOOKING_OVERDUE_NOTIFY_AFTER_MINUTES
            ),
        ).select_related("customer", "bike", "pickup_location")
        for booking in overdue_bookings.iterator():
            if notify_booking_event_once(
                booking,
                "return_overdue",
                BookingNotificationEvent.Audience.OPERATOR,
                deduplication_event=f"return_overdue:{booking.end_at.isoformat()}",
            ):
                sent += 1

        self.stdout.write(self.style.SUCCESS(f"Создано уведомлений: {sent}."))
