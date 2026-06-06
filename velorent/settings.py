import os
from pathlib import Path
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)

def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default=0):
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return int(value)


def env_list(name, default=""):
    return [
        value.strip()
        for value in os.getenv(name, default).split(",")
        if value.strip()
    ]


DEBUG = env_bool("DEBUG", True)
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "unsafe-dev-secret-key-change-me"
    else:
        raise ImproperlyConfigured("SECRET_KEY must be set when DEBUG=False.")
if not DEBUG and SECRET_KEY in {"unsafe-secret-key", "unsafe-dev-secret-key-change-me", "change-me"}:
    raise ImproperlyConfigured("Set a strong SECRET_KEY before running with DEBUG=False.")
ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    "127.0.0.1,localhost,192.168.0.14,.trycloudflare.com,.ngrok-free.app,.lhr.life",
)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts",
    "catalog",
    "rentals",
    "integrations",
    "dashboard",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.AuthenticatedPageNoStoreMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "velorent.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.unread_notifications",
                "accounts.context_processors.primary_pickup_location",
            ],
        },
    },
]

WSGI_APPLICATION = "velorent.wsgi.application"
ASGI_APPLICATION = "velorent.asgi.application"

db_engine = os.getenv("DB_ENGINE", "django.db.backends.sqlite3")
if db_engine == "django.db.backends.sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": db_engine,
            "NAME": BASE_DIR / os.getenv("DB_NAME", "db.sqlite3"),
        }
    }
else:
    database_config = {
        "ENGINE": db_engine,
        "NAME": os.getenv("DB_NAME", "velorent"),
        "USER": os.getenv("DB_USER", "velorent"),
        "PASSWORD": os.getenv("DB_PASSWORD", "velorent"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
    }
    if db_engine == "django.db.backends.mysql":
        database_config["OPTIONS"] = {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        }
    DATABASES = {"default": database_config}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Asia/Chita"
USE_I18N = True
USE_TZ = True

STATIC_URL = os.getenv("STATIC_URL", "/static/")
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / os.getenv("STATIC_ROOT", "staticfiles")
MEDIA_URL = os.getenv("MEDIA_URL", "/media/")
MEDIA_ROOT = BASE_DIR / os.getenv("MEDIA_ROOT", "media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
ACCOUNT_ACCESS_CODE_TTL_MINUTES = int(os.getenv("ACCOUNT_ACCESS_CODE_TTL_MINUTES", "30"))
ACCOUNT_ACCESS_CODE_MAX_ATTEMPTS = int(os.getenv("ACCOUNT_ACCESS_CODE_MAX_ATTEMPTS", "5"))
EMAIL_VERIFICATION_CODE_TTL_MINUTES = int(os.getenv("EMAIL_VERIFICATION_CODE_TTL_MINUTES", "20"))
EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS = int(os.getenv("EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS", "5"))
EMAIL_VERIFICATION_RESEND_SECONDS = int(os.getenv("EMAIL_VERIFICATION_RESEND_SECONDS", "60"))
PASSWORD_CHANGE_CODE_TTL_MINUTES = int(os.getenv("PASSWORD_CHANGE_CODE_TTL_MINUTES", "15"))
PASSWORD_CHANGE_CODE_MAX_ATTEMPTS = int(os.getenv("PASSWORD_CHANGE_CODE_MAX_ATTEMPTS", "5"))
PASSWORD_CHANGE_RESEND_SECONDS = int(os.getenv("PASSWORD_CHANGE_RESEND_SECONDS", "60"))
VK_CLIENT_ID = os.getenv("VK_CLIENT_ID", "")
VK_CLIENT_SECRET = os.getenv("VK_CLIENT_SECRET", "")
VK_REDIRECT_URI = os.getenv("VK_REDIRECT_URI", "")
VK_API_VERSION = os.getenv("VK_API_VERSION", "5.199")
VK_GROUP_TOKEN = os.getenv("VK_GROUP_TOKEN", "")
VK_COMMUNITY_URL = os.getenv("VK_COMMUNITY_URL", "")

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@velorent.local")
PERSONAL_DATA_EMAIL = os.getenv("PERSONAL_DATA_EMAIL", DEFAULT_FROM_EMAIL)
RENTAL_PROVIDER_NAME = os.getenv("RENTAL_PROVIDER_NAME", "ВелоРент")
RENTAL_PROVIDER_DETAILS = os.getenv("RENTAL_PROVIDER_DETAILS", "")
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "False").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").lower() == "true"
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
}

ONEC_API_URL = os.getenv("ONEC_API_URL", "")
ONEC_API_TOKEN = os.getenv("ONEC_API_TOKEN", "")
ONEC_API_TIMEOUT_SECONDS = env_int("ONEC_API_TIMEOUT_SECONDS", 10)
ONEC_SYNC_IMMEDIATE = env_bool("ONEC_SYNC_IMMEDIATE", False)

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0 if DEBUG else 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if env_bool("USE_X_FORWARDED_PROTO", False) else None

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"
