import hashlib
import json
from datetime import datetime
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from dashboard.data_inventory import build_data_inventory


class Command(BaseCommand):
    help = "Экспортирует данные в переносимый fixture и создает контрольный отчет."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default="backups/hosting_transfer",
            help="Каталог для fixture и контрольного отчета.",
        )

    def handle(self, *args, **options):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = Path(options["output_dir"]).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        fixture_path = output_dir / f"velorent-data-{stamp}.json"
        inventory_path = output_dir / f"velorent-inventory-{stamp}.json"

        with fixture_path.open("w", encoding="utf-8", newline="\n") as fixture_stream:
            call_command(
                "dumpdata",
                exclude=["contenttypes", "auth.permission", "sessions"],
                natural_foreign=True,
                natural_primary=True,
                indent=2,
                stdout=fixture_stream,
            )

        fixture_hash = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        inventory = {
            "created_at": timezone.now().isoformat(),
            "database_vendor": connection.vendor,
            "fixture_file": fixture_path.name,
            "fixture_sha256": fixture_hash,
            **build_data_inventory(),
        }
        inventory_path.write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        self.stdout.write(self.style.SUCCESS(f"Данные экспортированы: {fixture_path}"))
        self.stdout.write(self.style.SUCCESS(f"Контрольный файл: {inventory_path}"))
