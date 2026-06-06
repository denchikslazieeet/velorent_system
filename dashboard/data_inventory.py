from pathlib import Path

from django.apps import apps
from django.conf import settings


EXCLUDED_MODELS = {
    "auth.permission",
    "contenttypes.contenttype",
    "sessions.session",
}


def build_data_inventory():
    counts = {}
    for model in apps.get_models():
        label = model._meta.label_lower
        if label not in EXCLUDED_MODELS:
            counts[label] = model._default_manager.count()

    media_files = [
        path
        for path in Path(settings.MEDIA_ROOT).rglob("*")
        if path.is_file()
    ]
    return {
        "models": dict(sorted(counts.items())),
        "media_files": len(media_files),
    }
