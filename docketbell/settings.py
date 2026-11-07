"""Django settings for Docketbell.

Every deployment-specific value comes from an environment variable so the same
image runs in development, staging and production. See ``.env.example`` and the
"Configuration" section of the README for the full list.
"""

from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from django.conf.locale import LANG_INFO
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


def env_int(name: str, default: int) -> int:
    value = env(name)
    try:
        return int(value) if value else default
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be a whole number, got {value!r}") from exc


# --- Core -------------------------------------------------------------------

DEBUG = env_bool("DEBUG", default=False)

SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Set SECRET_KEY (or DEBUG=true for local development).")
    SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"  # noqa: S105

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "docketbell.core",
    "docketbell.sms",
    "docketbell.dashboard",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.humanize",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "docketbell.urls"
WSGI_APPLICATION = "docketbell.wsgi.application"

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
                "django.template.context_processors.i18n",
                "docketbell.dashboard.context_processors.docketbell",
            ],
        },
    },
]

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", f"sqlite:///{BASE_DIR.parent / 'db.sqlite3'}"),
        conn_max_age=env_int("DATABASE_CONN_MAX_AGE", 60),
        conn_health_checks=True,
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "login"

# --- Languages ----------------------------------------------------------------
#
# Two separate lists:
#   * DOCKETBELL_LANGUAGES - languages people can receive texts in.
#   * LANGUAGES            - languages the staff dashboard is translated into.
# Texts are the product, so every SMS language ships with full message copy.

LANG_INFO.setdefault(
    "ht",
    {"bidi": False, "code": "ht", "name": "Haitian Creole", "name_local": "Kreyòl ayisyen"},
)

DOCKETBELL_LANGUAGES = [
    ("en", "English"),
    ("es", "Español"),
    ("zh-hans", "中文（简体）"),
    ("vi", "Tiếng Việt"),
    ("ko", "한국어"),
    ("ru", "Русский"),
    ("ar", "العربية"),
    ("ht", "Kreyòl ayisyen"),
]

LANGUAGE_CODE = env("LANGUAGE_CODE", "en")
LANGUAGES = [("en", "English"), ("es", "Español")]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True

TIME_ZONE = env("TIME_ZONE", "America/New_York")
USE_TZ = True

# --- Static files -------------------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(env("STATIC_ROOT", str(BASE_DIR.parent / "staticfiles")))
if DEBUG:
    # In development WhiteNoise serves straight from the source folders; it only
    # needs STATIC_ROOT after collectstatic, so don't warn that it's missing.
    import warnings

    warnings.filterwarnings("ignore", message="No directory at", module="whitenoise.base")

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# --- Security -----------------------------------------------------------------

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 60 * 60 * 12)
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

if env_bool("BEHIND_HTTPS_PROXY", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", default=True)
    CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", default=True)
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=False)
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
    SECURE_REDIRECT_EXEMPT = [r"^healthz$"]

# --- Logging ------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "httpx": {"level": "WARNING"},
    },
}

# --- Docketbell ---------------------------------------------------------------

# Who the texts come from. Shown in every message, so keep it short and familiar.
DOCKETBELL_ORG_NAME = env("DOCKETBELL_ORG_NAME", "Court Reminders")
# Phone number people can call with questions. Shown in texts.
DOCKETBELL_ORG_PHONE = env("DOCKETBELL_ORG_PHONE", "")
# Public base URL (e.g. https://reminders.example.org). Used for webhook
# signature checks and delivery-status callbacks.
DOCKETBELL_PUBLIC_URL = env("DOCKETBELL_PUBLIC_URL").rstrip("/")

# Region used to read phone numbers written without a country code.
DOCKETBELL_PHONE_REGION = env("DOCKETBELL_PHONE_REGION", "US")
# Region used to pick date and time conventions, e.g. "US" gives es_US (2:30 p.m.).
DOCKETBELL_LOCALE_REGION = env("DOCKETBELL_LOCALE_REGION", "US")

# Reminder schedule: days before the court date. Default follows the NYC and
# Hennepin County studies: a week out, a few days out, and the day before.
DOCKETBELL_REMINDER_DAYS = [int(d) for d in env_list("DOCKETBELL_REMINDER_DAYS", "7,3,1")]
# Local time (court's time zone) scheduled reminders go out.
DOCKETBELL_SEND_TIME = env("DOCKETBELL_SEND_TIME", "10:00")
# Texts are only sent inside this local window; anything due outside waits.
DOCKETBELL_SEND_WINDOW = env("DOCKETBELL_SEND_WINDOW", "08:00-20:00")
# Text people who missed court, encouraging them to call before a warrant is served.
DOCKETBELL_SEND_MISSED_FOLLOW_UP = env_bool("DOCKETBELL_SEND_MISSED_FOLLOW_UP", default=True)
# Reply to STOP with a confirmation. Turn off if your provider already does
# (for example Twilio Advanced Opt-Out).
DOCKETBELL_SEND_OPT_OUT_CONFIRMATION = env_bool(
    "DOCKETBELL_SEND_OPT_OUT_CONFIRMATION", default=True
)

DOCKETBELL_MAX_ATTEMPTS = env_int("DOCKETBELL_MAX_ATTEMPTS", 3)
DOCKETBELL_WORKER_INTERVAL = env_int("DOCKETBELL_WORKER_INTERVAL", 15)
# Price of one SMS segment in USD, for cost estimates on the dashboard.
DOCKETBELL_COST_PER_SEGMENT = float(env("DOCKETBELL_COST_PER_SEGMENT", "0.0083"))
# Delete court dates, people and messages this many days after the court date.
# 0 keeps everything. Applied by ``manage.py purge_old_data``.
DOCKETBELL_RETENTION_DAYS = env_int("DOCKETBELL_RETENTION_DAYS", 0)
# Allow staff to simulate replies from the dashboard (training and demos).
DOCKETBELL_ALLOW_SIMULATED_REPLIES = env_bool("DOCKETBELL_ALLOW_SIMULATED_REPLIES", default=DEBUG)

# --- SMS ----------------------------------------------------------------------

SMS_BACKEND_ALIASES = {
    "console": "docketbell.sms.backends.console.ConsoleBackend",
    "locmem": "docketbell.sms.backends.locmem.LocmemBackend",
    "twilio": "docketbell.sms.backends.twilio.TwilioBackend",
    "http": "docketbell.sms.backends.http.HTTPGatewayBackend",
}
_backend = env("SMS_BACKEND", "console")
SMS_BACKEND = SMS_BACKEND_ALIASES.get(_backend, _backend)

TWILIO_ACCOUNT_SID = env("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = env("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = env("TWILIO_FROM_NUMBER")
TWILIO_MESSAGING_SERVICE_SID = env("TWILIO_MESSAGING_SERVICE_SID")
TWILIO_VALIDATE_SIGNATURES = env_bool("TWILIO_VALIDATE_SIGNATURES", default=True)

SMS_GATEWAY_URL = env("SMS_GATEWAY_URL")
SMS_GATEWAY_TOKEN = env("SMS_GATEWAY_TOKEN")
SMS_GATEWAY_INBOUND_TOKEN = env("SMS_GATEWAY_INBOUND_TOKEN")
SMS_GATEWAY_TIMEOUT = float(env("SMS_GATEWAY_TIMEOUT", "10"))
