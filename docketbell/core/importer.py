"""Import court dates from a CSV file.

Most offices can export a spreadsheet from their case management system, so
CSV is the simplest integration. Re-importing the same export is safe: rows
are matched on ``external_id`` (or person, court and time), new dates are
added, moved dates are rescheduled (and the person is told), and unchanged
rows are left alone.

Columns (header names are case-insensitive)::

    first_name*, phone*, court*, date*, time*,
    last_name, language, room, hearing_type, case_number, external_id

``date`` accepts 2026-11-17 or 11/17/2026. ``time`` accepts 14:30 or 2:30 PM.
``language`` accepts a code (es) or a name (Spanish, Español).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from docketbell.core import services
from docketbell.core.models import Court, CourtDate, Person
from docketbell.core.phone import normalize
from docketbell.core.replies import language_names, normalize_text

REQUIRED = ("first_name", "phone", "court", "date", "time")
OPTIONAL = ("last_name", "language", "room", "hearing_type", "case_number", "external_id")
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d")
TIME_FORMATS = ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%I %p", "%I%p")


class RowError(ValueError):
    pass


@dataclass
class ImportReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: list[tuple[int, str]] = field(default_factory=list)
    errors: list[tuple[int, str]] = field(default_factory=list)
    dry_run: bool = False

    @property
    def rows(self) -> int:
        return self.created + self.updated + self.unchanged + len(self.skipped) + len(self.errors)


def parse_date(value: str) -> dt.date:
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise RowError(
        _("Can't read the date %(value)r. Use 2026-11-17 or 11/17/2026.") % {"value": value}
    )


def parse_time(value: str) -> dt.time:
    value = " ".join(value.strip().upper().replace(".", "").split())
    for fmt in TIME_FORMATS:
        try:
            return dt.datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise RowError(_("Can't read the time %(value)r. Use 14:30 or 2:30 PM.") % {"value": value})


def parse_language(value: str) -> str:
    from django.conf import settings

    value = (value or "").strip()
    if not value:
        return "en"
    codes = {code.lower(): code for code, _name in settings.DOCKETBELL_LANGUAGES}
    if value.lower() in codes:
        return codes[value.lower()]
    if value.lower() in {"zh", "zh-cn", "chinese"}:
        return "zh-hans"
    found = language_names().get(normalize_text(value))
    if found:
        return found
    raise RowError(_("Unknown language %(value)r.") % {"value": value})


def _clean_headers(fieldnames: list[str] | None) -> list[str]:
    return [(name or "").strip().lower().replace(" ", "_") for name in fieldnames or []]


def import_court_dates(
    fileobj,
    *,
    user=None,
    dry_run: bool = False,
    notify: bool = True,
    now: dt.datetime | None = None,
) -> ImportReport:
    """Import rows from a CSV text stream. Bad rows are reported, good rows still import."""
    now = now or timezone.now()
    report = ImportReport(dry_run=dry_run)
    if isinstance(fileobj, bytes | bytearray):
        fileobj = fileobj.decode("utf-8-sig")
    if isinstance(fileobj, str):
        fileobj = io.StringIO(fileobj.removeprefix("\ufeff"))
    reader = csv.DictReader(fileobj)
    reader.fieldnames = _clean_headers(reader.fieldnames)
    missing = [name for name in REQUIRED if name not in reader.fieldnames]
    if missing:
        report.errors.append((1, _("Missing columns: %(names)s") % {"names": ", ".join(missing)}))
        return report

    courts = {court.name.casefold(): court for court in Court.objects.filter(is_active=True)}
    with transaction.atomic():
        for line, row in enumerate(reader, start=2):
            if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
                continue  # blank line
            try:
                with transaction.atomic():
                    outcome = _import_row(row, courts=courts, user=user, notify=notify, now=now)
            except RowError as exc:
                report.errors.append((line, str(exc)))
                continue
            if outcome.startswith("skipped:"):
                report.skipped.append((line, outcome.removeprefix("skipped:")))
            else:
                setattr(report, outcome, getattr(report, outcome) + 1)
        if dry_run:
            transaction.set_rollback(True)
    return report


def _value(row: dict, name: str) -> str:
    return (row.get(name) or "").strip()


def _import_row(row: dict, *, courts: dict, user, notify: bool, now: dt.datetime) -> str:
    first_name = _value(row, "first_name")
    if not first_name:
        raise RowError(_("first_name is empty."))
    phone = normalize(_value(row, "phone"))
    if phone is None:
        raise RowError(_("%(value)r isn't a valid phone number.") % {"value": _value(row, "phone")})
    court = courts.get(_value(row, "court").casefold())
    if court is None:
        raise RowError(
            _("Unknown court %(value)r. Add it in the admin first, or fix the spelling.")
            % {"value": _value(row, "court")}
        )
    starts_at = dt.datetime.combine(
        parse_date(_value(row, "date")), parse_time(_value(row, "time")), tzinfo=court.tzinfo
    )
    language = parse_language(_value(row, "language")) if row.get("language") else None
    external_id = _value(row, "external_id")
    last_name = _value(row, "last_name")

    person = Person.objects.filter(phone=phone, first_name__iexact=first_name).first()
    if person is None:
        person = Person.objects.create(
            first_name=first_name, last_name=last_name, phone=phone, language=language or "en"
        )
    else:
        changes = {}
        if language and person.language != language:
            changes["language"] = language
        if last_name and person.last_name != last_name:
            changes["last_name"] = last_name
        if changes:
            Person.objects.filter(pk=person.pk).update(**changes, updated_at=now)

    details = {
        "room": _value(row, "room"),
        "hearing_type": _value(row, "hearing_type"),
        "case_number": _value(row, "case_number"),
    }
    if external_id:
        court_date = CourtDate.objects.filter(external_id=external_id).first()
    else:
        court_date = CourtDate.objects.filter(
            person=person, court=court, starts_at=starts_at
        ).first()

    if court_date is None:
        if starts_at <= now:
            return "skipped:" + _("Court date is in the past.")
        court_date = CourtDate.objects.create(
            person=person,
            court=court,
            starts_at=starts_at,
            external_id=external_id,
            created_by=user,
            **details,
        )
        services.enroll(court_date, now=now)
        return "created"

    changed = False
    updates = {k: v for k, v in details.items() if v and getattr(court_date, k) != v}
    if court_date.person_id != person.pk:
        updates["person"] = person
    if court_date.court_id != court.pk:
        updates["court"] = court
    if updates:
        for key, value in updates.items():
            setattr(court_date, key, value)
        court_date.save()
        changed = True
    if court_date.starts_at != starts_at:
        if starts_at <= now:
            return "skipped:" + _("New date is in the past.")
        services.reschedule(court_date, starts_at, notify=notify, now=now)
        changed = True
    return "updated" if changed else "unchanged"


TEMPLATE_CSV = (
    "first_name,last_name,phone,language,court,date,time,room,hearing_type,case_number,external_id\n"
    "Maria,Lopez,(555) 010-0142,es,Main Street Courthouse,2026-12-01,9:30 AM,Courtroom 4B,"
    "Arraignment,CR-2026-0193,case-0193\n"
)
