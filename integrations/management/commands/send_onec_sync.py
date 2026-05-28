from django.core.management.base import BaseCommand

from integrations.models import SyncEvent
from integrations.services import send_sync_event


class Command(BaseCommand):
    help = "Send pending 1C sync events."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        limit = max(options["limit"], 1)
        events = SyncEvent.objects.filter(
            direction=SyncEvent.Direction.TO_ONEC,
            status__in=[SyncEvent.Status.PENDING, SyncEvent.Status.FAILED],
        ).order_by("created_at")[:limit]

        sent = 0
        failed = 0
        for event in events:
            if send_sync_event(event):
                sent += 1
            else:
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(f"1C sync complete. Sent: {sent}. Failed: {failed}.")
        )
