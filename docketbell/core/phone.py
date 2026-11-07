"""Phone number helpers. Numbers are stored in E.164 (``+12125550123``)."""

from __future__ import annotations

import phonenumbers
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


def normalize(raw: str, region: str | None = None) -> str | None:
    """Return the number in E.164 form, or ``None`` if it isn't a valid number."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        parsed = phonenumbers.parse(raw, region or settings.DOCKETBELL_PHONE_REGION)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_or_raise(raw: str) -> str:
    number = normalize(raw)
    if number is None:
        raise ValidationError(
            _("%(number)s doesn't look like a valid mobile number."),
            code="invalid_phone",
            params={"number": raw},
        )
    return number


def display(e164: str) -> str:
    """Format for people: national format at home, international otherwise."""
    if not e164:
        return ""
    try:
        parsed = phonenumbers.parse(e164, None)
    except phonenumbers.NumberParseException:
        return e164
    region = phonenumbers.region_code_for_number(parsed)
    fmt = (
        phonenumbers.PhoneNumberFormat.NATIONAL
        if region == settings.DOCKETBELL_PHONE_REGION
        else phonenumbers.PhoneNumberFormat.INTERNATIONAL
    )
    return phonenumbers.format_number(parsed, fmt)


def mask(e164: str) -> str:
    """Hide all but the last four digits, for logs."""
    if not e164 or len(e164) < 5:
        return "***"
    return "***" + e164[-4:]
