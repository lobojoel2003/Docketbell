"""Dates and times written the way each language writes them.

Formatting uses CLDR data through Babel, so "Tuesday, November 17" becomes
"martes, 17 de noviembre", "11月17日星期二" or "вторник, 17 ноября" without
hand-written patterns. Haitian Creole is not fully covered by CLDR yet, so it
gets its own day and month names.
"""

from __future__ import annotations

import datetime as dt
import re
from functools import lru_cache

from babel import Locale, UnknownLocaleError, localedata
from babel.dates import format_datetime, match_skeleton
from django.conf import settings
from django.utils.translation import to_locale

# Monday first, matching datetime.weekday().
_HT_DAYS = ("lendi", "madi", "mèkredi", "jedi", "vandredi", "samdi", "dimanch")
_HT_MONTHS = (
    "janvye",
    "fevriye",
    "mas",
    "avril",
    "me",
    "jen",
    "jiyè",
    "out",
    "septanm",
    "oktòb",
    "novanm",
    "desanm",
)

# Time patterns that read better than the CLDR "short" default for people in
# the US: 오후 2:30 instead of PM 2:30, 下午2:30 instead of 14:30.
_TIME_PATTERNS = {
    "ko": "aaaa h:mm",
    "zh-hans": "aaaah:mm",
}


# CLDR uses narrow and regular no-break spaces ("2:30\u202fPM"). Either one
# forces the whole text into UCS-2 and doubles its cost, so use plain spaces.
_SPACES = str.maketrans({"\u202f": " ", "\u00a0": " ", "\u2009": " "})


def _plain(text: str) -> str:
    return text.translate(_SPACES)


@lru_cache(maxsize=64)
def babel_locale(language: str) -> str:
    """Pick the most specific Babel locale for a Django language code."""
    base = to_locale(language or "en")
    region = settings.DOCKETBELL_LOCALE_REGION
    candidates = [f"{base}_{region}"] if region and "_" not in base else []
    candidates += [base, base.split("_")[0], "en_US"]
    for candidate in candidates:
        if localedata.exists(candidate):
            return candidate
    return "en_US"  # pragma: no cover - en_US always exists


def _widen(pattern: str) -> str:
    """Use full weekday and month names: "Tue, Nov 17" -> "Tuesday, November 17".

    Text inside single quotes is literal in CLDR patterns and is left alone.
    """
    parts = pattern.split("'")
    for i in range(0, len(parts), 2):  # even parts are outside quotes
        part = re.sub(r"(?<![Ec])([Ec])\1{0,2}(?![Ec])", lambda m: m.group(1) * 4, parts[i])
        parts[i] = re.sub(r"(?<![ML])([ML])\1{2}(?![ML])", lambda m: m.group(1) * 4, part)
    return "'".join(parts)


@lru_cache(maxsize=64)
def _date_pattern(locale_id: str) -> str:
    locale = Locale.parse(locale_id)
    skeletons = locale.datetime_skeletons
    match = match_skeleton("MMMMEEEEd", skeletons.keys())
    if match is None:  # pragma: no cover - every CLDR locale has a weekday skeleton
        return "EEEE d MMMM"
    return _widen(str(skeletons[match].pattern))


def format_date(moment: dt.datetime | dt.date, language: str) -> str:
    """Weekday, month and day, e.g. "Tuesday, November 17"."""
    if language == "ht":
        return f"{_HT_DAYS[moment.weekday()]} {moment.day} {_HT_MONTHS[moment.month - 1]}"
    locale_id = babel_locale(language)
    value = moment if isinstance(moment, dt.datetime) else dt.datetime.combine(moment, dt.time(12))
    return _plain(format_datetime(value, _date_pattern(locale_id), locale=locale_id))


def format_time(moment: dt.datetime, language: str) -> str:
    """Clock time, e.g. "9:30 AM" or "9:30 a.m." or "09:30"."""
    if language == "ht":
        return _plain(format_datetime(moment, "h:mm a", locale="en_US"))
    locale_id = babel_locale(language)
    pattern = _TIME_PATTERNS.get(language)
    if pattern is None:
        try:
            pattern = str(Locale.parse(locale_id).time_formats["short"].pattern)
        except (UnknownLocaleError, KeyError):  # pragma: no cover
            pattern = "HH:mm"
    return _plain(format_datetime(moment, pattern, locale=locale_id))
