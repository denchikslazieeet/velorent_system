import json
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from dashboard.data_inventory import build_data_inventory


class Command(BaseCommand):
    help = "Импортирует переносимый fixture только в пустую рабочую базу."

    def add_arguments(self, parser):
        parser.add_argument("fixture", help="Путь к JSON-файлу, созданному export_portable_data.")
        parser.add_argument(
            "--allow-nonempty",
            action="store_true",
            help="Разрешить импорт в базу, где уже есть рабочие записи.",
        )
        parser.add_argument("--inventory-output", help="Путь для контрольного JSON после импорта.")

    def handle(self, *args, **options):
        fixture_path = Path(options["fixture"]).resolve()
        if not fixture_path.is_file():
            raise CommandError(f"Fixture не найден: {fixture_path}")

        before = build_data_inventory()
        nonempty = {
            label: count
            for label, count in before["models"].items()
            if count
        }
        if nonempty and not options["allow_nonempty"]:
            details = ", ".join(f"{label}={count}" for label, count in nonempty.items())
            raise CommandError(
                "Целевая база не пустая. Импорт остановлен, чтобы не смешать данные. "
                f"Найдены записи: {details}"
            )

        call_command("loaddata", str(fixture_path))
        inventory = build_data_inventory()
        rendered = json.dumps(inventory, ensure_ascii=False, indent=2)

        if options["inventory_output"]:
            inventory_path = Path(options["inventory_output"]).resolve()
            inventory_path.parent.mkdir(parents=True, exist_ok=True)
            inventory_path.write_text(rendered + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Контрольный файл создан: {inventory_path}"))

        self.stdout.write(self.style.SUCCESS(f"Данные импортированы из {fixture_path}"))
