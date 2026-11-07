"""The words people receive.

The texts are the product. They follow what research on court reminders has
found works (ideas42, the NYC Criminal Court study, J-PAL):

* Be specific: name, day, time and place in every reminder.
* Say plainly what happens if someone misses court, without threatening them.
* Prompt a plan: rides, time off work, childcare.
* Make it easy to answer: reply 1 or 2, which works in any language and on any keyboard.
* Offer a person to talk to, and a phone number.
* Keep it short, and never include charges or case details.

Each text is a translatable string with ``{placeholders}``. Staff can override
any text per language from the admin (``MessageTemplate``) without a deploy.
English copy sticks to the GSM-7 character set (straight quotes, no dashes)
so each text costs as few SMS segments as possible.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone, translation
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from docketbell.core import formatting

if TYPE_CHECKING:
    from docketbell.core.models import CourtDate, Person


class Kind:
    # Scheduled reminders (match Reminder.Kind values).
    ENROLLMENT = "enrollment"
    HEADS_UP = "heads_up"
    PLAN = "plan"
    TOMORROW = "tomorrow"
    TODAY = "today"
    RESCHEDULED = "rescheduled"
    CANCELED = "canceled"
    MISSED = "missed"
    # Automatic answers to replies.
    REPLY_CONFIRMED = "reply_confirmed"
    REPLY_HELP = "reply_help"
    REPLY_STOP = "reply_stop"
    REPLY_START = "reply_start"
    REPLY_INFO = "reply_info"
    REPLY_UNKNOWN = "reply_unknown"
    REPLY_NO_COURT_DATE = "reply_no_court_date"
    REPLY_LANGUAGE = "reply_language"


@dataclass(frozen=True)
class Spec:
    kind: str
    label: Promise
    when: Promise
    text: Promise
    group: str  # "reminder" or "reply"


SPECS: tuple[Spec, ...] = (
    Spec(
        Kind.ENROLLMENT,
        _("Welcome"),
        _("Right after someone is signed up for reminders."),
        # Translators: SMS. Sent when someone is signed up. Keep it short and
        # warm. Keep every {placeholder}, "1" and "STOP" exactly as written.
        _(
            "Hi {first_name}, this is {org_name}. We'll text you reminders before your "
            "court date: {date} at {time}, {place}. Reply 1 to confirm you got this. "
            "Reply STOP to opt out."
        ),
        "reminder",
    ),
    Spec(
        Kind.HEADS_UP,
        _("Heads-up"),
        _("The first countdown reminder, usually a week before. Explains what is at stake."),
        # Translators: SMS. Explains the consequence of missing court plainly
        # but kindly. Keep {placeholders}, "1" and "2" exactly as written.
        _(
            "{first_name}, your court date is {date} at {time}, {place}. If you miss it, "
            "the judge may issue a warrant for your arrest. Reply 1 to confirm, or 2 if "
            "you need help."
        ),
        "reminder",
    ),
    Spec(
        Kind.PLAN,
        _("Make a plan"),
        _("Later countdown reminders, usually 3 days before. Prompts a plan to get there."),
        # Translators: SMS. Encourages the person to plan transport, work and
        # childcare. Keep {placeholders} and "2" exactly as written.
        _(
            "{first_name}, your court date is {date} at {time}. Make a plan now: how "
            "you'll get there, and time off work or childcare if you need it. Reply 2 if "
            "something could stop you from going."
        ),
        "reminder",
    ),
    Spec(
        Kind.TOMORROW,
        _("Day before"),
        _("The day before the court date."),
        # Translators: SMS sent the day before court. Keep {placeholders}.
        _(
            "Reminder: your court date is tomorrow, {date} at {time}, {place}. Please "
            "arrive early. Missing court can lead to a warrant. Questions? Call {org_phone}."
        ),
        "reminder",
    ),
    Spec(
        Kind.TODAY,
        _("Morning of"),
        _("The morning of the court date (only if 0 is in the reminder schedule)."),
        # Translators: SMS sent the morning of court. Keep {placeholders}.
        _(
            "Today: your court date is at {time}, {place}. Please arrive early. If you "
            "are running late, call {org_phone}."
        ),
        "reminder",
    ),
    Spec(
        Kind.RESCHEDULED,
        _("Date changed"),
        _("When staff change the date or time."),
        # Translators: SMS sent when a court date moves. Keep {placeholders} and "1".
        _(
            "{first_name}, your court date has changed. The new date is {date} at {time}, "
            "{place}. Please go on the new date. Reply 1 to confirm."
        ),
        "reminder",
    ),
    Spec(
        Kind.CANCELED,
        _("Date canceled"),
        _("When staff cancel a court date."),
        # Translators: SMS sent when a court date is canceled. {date} is the old date.
        _(
            "{first_name}, your court date on {date} was canceled. You do not need to go "
            "to court that day. We'll text you if a new date is set. Questions? Call "
            "{org_phone}."
        ),
        "reminder",
    ),
    Spec(
        Kind.MISSED,
        _("Missed court"),
        _("After staff mark a court date as missed. Encourages a quick call back."),
        # Translators: SMS sent after someone may have missed court. Should feel
        # hopeful, not scary. {date} is the missed date. Keep {placeholders}.
        _(
            "{first_name}, our records show you may have missed court on {date}. It's not "
            "too late to fix this. Call {org_phone} today and we'll help you get a new date."
        ),
        "reminder",
    ),
    Spec(
        Kind.REPLY_CONFIRMED,
        _("Thanks for confirming"),
        _("When someone replies 1 or YES."),
        # Translators: SMS reply after someone confirms. Keep {placeholders} and "2".
        _(
            "Thank you, {first_name}. You're confirmed for {date} at {time}. If anything "
            "changes, reply 2 or call {org_phone}."
        ),
        "reply",
    ),
    Spec(
        Kind.REPLY_HELP,
        _("Help is on the way"),
        _("When someone replies 2 or NO. Also flags the court date for staff."),
        # Translators: SMS reply after someone asks for help. Keep {placeholders}.
        _(
            "Thanks for telling us, {first_name}. Someone from {org_name} will contact you "
            "soon. You can also call {org_phone}. Please don't skip court without talking "
            "to us first."
        ),
        "reply",
    ),
    Spec(
        Kind.REPLY_STOP,
        _("Opted out"),
        _("When someone replies STOP."),
        # Translators: SMS reply to STOP. Keep "START" in Latin letters.
        _(
            "You won't get more texts from {org_name}. Reply START to get reminders again. "
            "Questions about your case? Call {org_phone}."
        ),
        "reply",
    ),
    Spec(
        Kind.REPLY_START,
        _("Opted back in"),
        _("When someone replies START after opting out."),
        # Translators: SMS reply to START. Keep "STOP" in Latin letters.
        _("You'll get court date reminders from {org_name} again. Reply STOP to opt out."),
        "reply",
    ),
    Spec(
        Kind.REPLY_INFO,
        _("Help and info"),
        _("When someone replies HELP or INFO."),
        # Translators: SMS reply to HELP. Keep "1", "2" and "STOP" as written.
        _(
            "{org_name}: court date reminders. Reply 1 to confirm your date, 2 if you need "
            "help. Call {org_phone} with questions. Reply STOP to opt out. Msg & data rates "
            "may apply."
        ),
        "reply",
    ),
    Spec(
        Kind.REPLY_UNKNOWN,
        _("Didn't understand"),
        _("When a reply isn't a keyword. Sent at most once a day; staff see the message."),
        # Translators: SMS reply when we couldn't understand a message. Keep "1" and "2".
        _(
            "Sorry, we couldn't read that. Reply 1 to confirm your court date or 2 if you "
            "need help. A staff member will also read your message."
        ),
        "reply",
    ),
    Spec(
        Kind.REPLY_NO_COURT_DATE,
        _("No upcoming date"),
        _("When someone confirms but has no upcoming court date on file."),
        # Translators: SMS reply. Keep {placeholders}.
        _(
            "Thanks. We don't see an upcoming court date for you. If you think that's "
            "wrong, call {org_phone}."
        ),
        "reply",
    ),
    Spec(
        Kind.REPLY_LANGUAGE,
        _("Language changed"),
        _("When someone texts the name of a language, such as ESPAÑOL."),
        # Translators: SMS reply confirming the language switch. Name YOUR
        # language here (for Spanish: "en español"). Keep "STOP".
        _("OK. We'll text you in English from now on. Reply STOP to opt out."),
        "reply",
    ),
)

KINDS: dict[str, Spec] = {spec.kind: spec for spec in SPECS}

PLACEHOLDERS: dict[str, Promise] = {
    "first_name": _("Person's first name"),
    "org_name": _("Your organization's name"),
    "org_phone": _("Your phone number for questions"),
    "date": _("Court date, e.g. Tuesday, November 17"),
    "time": _("Court time, e.g. 9:30 AM"),
    "place": _("Court, room and address on one line"),
    "court_name": _("Court name"),
    "court_address": _("Court address"),
    "room": _("Courtroom"),
}

_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")


def placeholders_in(text: str) -> set[str]:
    return set(_PLACEHOLDER_RE.findall(text))


def unknown_placeholders(text: str) -> set[str]:
    return placeholders_in(text) - set(PLACEHOLDERS)


# Small grammar fixes that depend on the values filled in, per language.
_POLISH: dict[str, list[tuple[re.Pattern[str], str]]] = {
    # "a las 1:30 p.m." -> "a la 1:30 p.m." (one o'clock takes the singular article)
    "es": [(re.compile(r"\b([Ll])as (1:\d\d)"), r"\1a \2")],
}


def fill(template: str, context: dict[str, str], language: str = "") -> str:
    """Substitute ``{placeholders}`` in one pass, so values are never re-expanded."""
    text = _PLACEHOLDER_RE.sub(lambda m: str(context.get(m.group(1), m.group(0))), template)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.])", r"\1", text)
    text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)  # "9:30 p.m.." -> "9:30 p.m."
    for pattern, replacement in _POLISH.get(language, ()):
        text = pattern.sub(replacement, text)
    return text.strip()


def org_phone(court_date: CourtDate | None = None) -> str:
    if settings.DOCKETBELL_ORG_PHONE:
        return settings.DOCKETBELL_ORG_PHONE
    if court_date is not None and court_date.court.phone:
        return court_date.court.phone
    return ""


def build_context(
    *,
    language: str,
    person: Person | None = None,
    court_date: CourtDate | None = None,
) -> dict[str, str]:
    context = {
        "first_name": person.first_name if person else "",
        "org_name": settings.DOCKETBELL_ORG_NAME,
        "org_phone": org_phone(court_date),
        "date": "",
        "time": "",
        "place": "",
        "court_name": "",
        "court_address": "",
        "room": "",
    }
    if court_date is not None:
        local = timezone.localtime(court_date.starts_at, court_date.court.tzinfo)
        context.update(
            date=formatting.format_date(local, language),
            time=formatting.format_time(local, language),
            place=court_date.place,
            court_name=court_date.court.name,
            court_address=court_date.court.address,
            room=court_date.room,
        )
    return context


def template_for(kind: str, language: str) -> tuple[str, bool]:
    """Return ``(template, is_custom)`` for a message kind in a language."""
    from docketbell.core.models import MessageTemplate

    custom = (
        MessageTemplate.objects.filter(kind=kind, language=language, is_active=True)
        .values_list("body", flat=True)
        .first()
    )
    if custom:
        return custom, True
    with translation.override(language):
        return str(KINDS[kind].text), False


def render(kind: str, language: str, context: dict[str, str]) -> str:
    template, _custom = template_for(kind, language)
    return fill(template, context, language)


def render_for(
    kind: str, *, person: Person, court_date: CourtDate | None = None, language: str | None = None
) -> str:
    language = language or person.language
    return render(
        kind, language, build_context(language=language, person=person, court_date=court_date)
    )


# --- Sample data for previews -------------------------------------------------

SAMPLE_NAMES = {
    "en": "Maria",
    "es": "María",
    "zh-hans": "Wei",
    "vi": "Linh",
    "ko": "Min-jun",
    "ru": "Olga",
    "ar": "Amina",
    "ht": "Jean",
}


def sample_context(language: str, now: dt.datetime | None = None) -> dict[str, str]:
    """Realistic values for previews: next Tuesday at 9:30 AM."""
    tz = timezone.get_default_timezone()
    today = timezone.localtime(now or timezone.now(), tz).date()
    days_ahead = (1 - today.weekday()) % 7 or 7
    when = dt.datetime.combine(today + dt.timedelta(days=days_ahead), dt.time(9, 30), tzinfo=tz)
    court, room, address = "Main Street Courthouse", "Courtroom 4B", "100 Main St"
    return {
        "first_name": SAMPLE_NAMES.get(language, "Maria"),
        "org_name": settings.DOCKETBELL_ORG_NAME,
        "org_phone": settings.DOCKETBELL_ORG_PHONE or "(555) 010-0199",
        "date": formatting.format_date(when, language),
        "time": formatting.format_time(when, language),
        "place": f"{court}, {room}, {address}",
        "court_name": court,
        "court_address": address,
        "room": room,
    }
