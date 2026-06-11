from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from integrations.email_delivery import attempt_email_delivery
from integrations.models import EmailDelivery


class Command(BaseCommand):
    help = "Повторно отправляет письма, которые не удалось доставить сразу."

    def handle(self, *args, **options):
        deliveries = EmailDelivery.objects.filter(
            status__in=[EmailDelivery.Status.PENDING, EmailDelivery.Status.FAILED],
            attempts__lt=settings.EMAIL_MAX_ATTEMPTS,
            next_attempt_at__lte=timezone.now(),
        ).order_by("created_at")

        sent = 0
        failed = 0
        for delivery in deliveries.iterator():
            if attempt_email_delivery(delivery):
                sent += 1
            else:
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(f"Отправлено: {sent}. Осталось с ошибкой: {failed}.")
        )
