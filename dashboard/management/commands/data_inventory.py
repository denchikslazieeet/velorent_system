import json
from pathlib import Path

from django.core.management.base import BaseCommand

from dashboard.data_inventory import build_data_inventory


class Command(BaseCommand):
    help = "Выводит контрольное количество записей и медиафайлов."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Путь для сохранения JSON-отчета.")

    def handle(self, *args, **options):
        inventory = build_data_inventory()
        rendered = json.dumps(inventory, ensure_ascii=False, indent=2)
        if options["output"]:
            output_path = Path(options["output"]).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Контрольный файл создан: {output_path}"))
        else:
            self.stdout.write(rendered)
