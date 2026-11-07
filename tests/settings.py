"""Settings for the test suite. Uses Postgres when DATABASE_URL is set (as in CI)."""

import os

os.environ.setdefault("SECRET_KEY", "tests-only-secret-key")
os.environ.setdefault("DOCKETBELL_ORG_NAME", "Main Street Defenders")
os.environ.setdefault("DOCKETBELL_ORG_PHONE", "(212) 555-0199")

import tempfile

from docketbell.settings import *  # noqa: F403

STATIC_ROOT = tempfile.mkdtemp(prefix="docketbell-static-")
SMS_BACKEND = "docketbell.sms.backends.locmem.LocmemBackend"
TIME_ZONE = "America/New_York"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
DOCKETBELL_ALLOW_SIMULATED_REPLIES = True
DOCKETBELL_PUBLIC_URL = "https://reminders.example.org"
TWILIO_AUTH_TOKEN = "test-auth-token"
SMS_GATEWAY_INBOUND_TOKEN = "gateway-inbound-token"
LOGGING = {"version": 1, "disable_existing_loggers": False}
