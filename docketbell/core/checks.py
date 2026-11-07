"""Startup checks (``manage.py check``) that catch configuration mistakes early."""

from __future__ import annotations

import gettext
import zoneinfo

from django.conf import settings
from django.core.checks import Error, Warning, register
from django.utils.translation import to_locale


@register("docketbell")
def check_configuration(app_configs=None, **kwargs):
    from docketbell.core import services

    problems = []

    try:
        start, end = services.send_window()
        send_time = services.parse_clock(settings.DOCKETBELL_SEND_TIME)
    except (ValueError, AttributeError):
        problems.append(
            Error(
                "DOCKETBELL_SEND_WINDOW must look like 08:00-20:00 and DOCKETBELL_SEND_TIME "
                "like 10:00.",
                id="docketbell.E001",
            )
        )
    else:
        if start >= end:
            problems.append(
                Error("DOCKETBELL_SEND_WINDOW must start before it ends.", id="docketbell.E002")
            )
        elif not start <= send_time < end:
            problems.append(
                Error(
                    "DOCKETBELL_SEND_TIME must fall inside DOCKETBELL_SEND_WINDOW.",
                    id="docketbell.E003",
                )
            )

    days = settings.DOCKETBELL_REMINDER_DAYS
    if not days or any(d < 0 or d > 60 for d in days):
        problems.append(
            Error(
                "DOCKETBELL_REMINDER_DAYS must be a list of days between 0 and 60, e.g. 7,3,1.",
                id="docketbell.E004",
            )
        )

    try:
        zoneinfo.ZoneInfo(settings.TIME_ZONE)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        problems.append(
            Error(f"TIME_ZONE {settings.TIME_ZONE!r} is unknown.", id="docketbell.E005")
        )

    if not settings.DOCKETBELL_ORG_PHONE:
        problems.append(
            Warning(
                "DOCKETBELL_ORG_PHONE is not set. Texts tell people to call this number "
                "with questions; without it, each court's own phone number is used.",
                id="docketbell.W001",
            )
        )

    missing = [
        code
        for code, _name in settings.DOCKETBELL_LANGUAGES
        if code != "en"
        and gettext.find("django", str(settings.LOCALE_PATHS[0]), [to_locale(code)]) is None
    ]
    if missing:
        problems.append(
            Warning(
                "Translations are not compiled for: "
                + ", ".join(missing)
                + ". Texts in these languages would fall back to English.",
                hint="Run: python manage.py compilemessages",
                id="docketbell.W002",
            )
        )

    if settings.SMS_BACKEND.endswith("ConsoleBackend") and not settings.DEBUG:
        problems.append(
            Warning(
                "SMS_BACKEND is 'console': texts are printed, not sent.",
                hint="Set SMS_BACKEND=twilio or SMS_BACKEND=http for real texts.",
                id="docketbell.W003",
            )
        )
    return problems
