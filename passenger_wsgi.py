import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
HOSTING_DATA_ROOT = PROJECT_ROOT.parent.parent
VENV_ROOT = Path(os.getenv("VEL_RENT_VENV", HOSTING_DATA_ROOT / "velorentenv"))

for site_packages in VENV_ROOT.glob("lib/python*/site-packages"):
    sys.path.insert(0, str(site_packages))

sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "velorent.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
