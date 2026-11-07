"""Scheduling and sending.

Reminders are rows in the database with a ``send_at`` time. A worker
(``manage.py run_worker``, or ``send_due_reminders`` from cron) picks up the
ones that are due and sends them. Rows are claimed with
``SELECT ... FOR UPDATE SKIP LOCKED``, so several workers can run at once
without sending anything twice.

Texts are rendered at send time, so a reminder always shows the court date as
it is *now*, even if staff edited it after the reminder was scheduled.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from docketbell.core import copy
from docketbell.core.models import CourtDate, Heartbeat, Message, Person, Reminder
from docketbell.core.phone import mask
from docketbell.sms import BaseBackend, SMSError, get_backend
from docketbell.sms.segments import analyze
from docketbell.version import build_info

log = logging.getLogger("docketbell")

Kind = Reminder.Kind


# --- Time helpers -------------------------------------------------------------


def parse_clock(value: str) -> dt.time:
    hours, minutes = value.strip().split(":")
    return dt.time(int(hours), int(minutes))


@lru_cache(maxsize=8)
def _window(spec: str) -> tuple[dt.time, dt.time]:
    start, end = spec.split("-")
    return parse_clock(start), parse_clock(end)


def send_window() -> tuple[dt.time, dt.time]:
    return _window(settings.DOCKETBELL_SEND_WINDOW)


def next_send_time(moment: dt.datetime, tz: dt.tzinfo) -> dt.datetime:
    """The first moment at or after ``moment`` that falls inside the send window."""
    start, end = send_window()
    local = moment.astimezone(tz)
    if local.time() < start:
        return dt.datetime.combine(local.date(), start, tzinfo=tz)
    if local.time() >= end:
        return dt.datetime.combine(local.date() + dt.timedelta(days=1), start, tzinfo=tz)
    return moment


# --- Planning -----------------------------------------------------------------


def plan_reminders(court_date: CourtDate, now: dt.datetime) -> list[tuple[str, dt.datetime]]:
    """Countdown reminders for a court date: ``[(kind, send_at), ...]``.

    The first multi-day reminder still in the future is the "heads-up" that
    explains what is at stake; later ones prompt a plan. Reminders whose time
    has already passed are left out.
    """
    tz = court_date.court.tzinfo
    starts_local = court_date.starts_at.astimezone(tz)
    send_time = parse_clock(settings.DOCKETBELL_SEND_TIME)
    window_start, _ = send_window()

    plan: list[tuple[str, dt.datetime]] = []
    seen: set[dt.datetime] = set()
    heads_up_sent = False
    for days in sorted(set(settings.DOCKETBELL_REMINDER_DAYS), reverse=True):
        day = starts_local.date() - dt.timedelta(days=days)
        if days == 0:
            kind = Kind.TODAY
            send_at = dt.datetime.combine(day, window_start, tzinfo=tz)
            if send_at > court_date.starts_at - dt.timedelta(hours=1):
                continue
        else:
            send_at = dt.datetime.combine(day, send_time, tzinfo=tz)
            if days == 1:
                kind = Kind.TOMORROW
            elif not heads_up_sent and send_at > now:
                kind = Kind.HEADS_UP
            else:
                kind = Kind.PLAN
        if send_at <= now or send_at in seen:
            continue
        if kind == Kind.HEADS_UP:
            heads_up_sent = True
        seen.add(send_at)
        plan.append((kind, send_at))
    return plan


def countdown_schedule() -> list[tuple[str, int]]:
    """The countdown for a court date booked well ahead: ``[(kind, days_before), ...]``."""
    schedule_: list[tuple[str, int]] = []
    heads_up = False
    for days in sorted(set(settings.DOCKETBELL_REMINDER_DAYS), reverse=True):
        if days == 0:
            kind = Kind.TODAY
        elif days == 1:
            kind = Kind.TOMORROW
        elif not heads_up:
            kind, heads_up = Kind.HEADS_UP, True
        else:
            kind = Kind.PLAN
        schedule_.append((kind, days))
    return schedule_


@transaction.atomic
def schedule(court_date: CourtDate, *, now: dt.datetime | None = None) -> list[Reminder]:
    """(Re)build the countdown reminders for a court date."""
    now = now or timezone.now()
    court_date.reminders.filter(status=Reminder.Status.PENDING, kind__in=Reminder.COUNTDOWN).update(
        status=Reminder.Status.CANCELED, detail="Replaced by a new schedule", updated_at=now
    )
    if court_date.status != CourtDate.Status.SCHEDULED:
        return []
    return Reminder.objects.bulk_create(
        Reminder(court_date=court_date, kind=kind, send_at=send_at, created_at=now)
        for kind, send_at in plan_reminders(court_date, now)
    )


def queue_now(court_date: CourtDate, kind: str, *, now: dt.datetime | None = None) -> Reminder:
    """Queue a one-off text (welcome, date changed, ...) for the next send window."""
    now = now or timezone.now()
    return Reminder.objects.create(
        court_date=court_date,
        kind=kind,
        send_at=next_send_time(now, court_date.court.tzinfo),
        created_at=now,
    )


def _cancel_pending(court_date: CourtDate, now: dt.datetime, reason: str, kinds=None) -> int:
    pending = court_date.reminders.filter(status=Reminder.Status.PENDING)
    if kinds is not None:
        pending = pending.filter(kind__in=kinds)
    return pending.update(status=Reminder.Status.CANCELED, detail=reason, updated_at=now)


def _has_been_texted(court_date: CourtDate) -> bool:
    return court_date.messages.filter(
        direction=Message.Direction.OUTBOUND,
        status__in=[Message.Status.SENT, Message.Status.DELIVERED],
    ).exists()


# --- Court date lifecycle -----------------------------------------------------


@transaction.atomic
def enroll(court_date: CourtDate, *, now: dt.datetime | None = None) -> None:
    """Start reminders for a new court date: a welcome text, then the countdown."""
    now = now or timezone.now()
    if court_date.status != CourtDate.Status.SCHEDULED or court_date.starts_at <= now:
        return
    queue_now(court_date, Kind.ENROLLMENT, now=now)
    schedule(court_date, now=now)


@transaction.atomic
def reschedule(
    court_date: CourtDate,
    starts_at: dt.datetime,
    *,
    notify: bool = True,
    now: dt.datetime | None = None,
) -> bool:
    """Move a court date. Returns True if the date actually changed."""
    now = now or timezone.now()
    if court_date.starts_at == starts_at and court_date.status == CourtDate.Status.SCHEDULED:
        return False
    texted = _has_been_texted(court_date)
    court_date.starts_at = starts_at
    court_date.status = CourtDate.Status.SCHEDULED
    court_date.confirmed_at = None  # they confirmed the old date, not this one
    court_date.save(update_fields=["starts_at", "status", "confirmed_at", "updated_at"])
    _cancel_pending(
        court_date, now, "Court date changed", kinds=[Kind.RESCHEDULED, Kind.CANCELED, Kind.MISSED]
    )
    if starts_at <= now:
        _cancel_pending(court_date, now, "Court date is in the past")
        return True
    if texted and notify:
        queue_now(court_date, Kind.RESCHEDULED, now=now)
    elif not court_date.reminders.filter(
        kind=Kind.ENROLLMENT, status__in=[Reminder.Status.PENDING, Reminder.Status.SENT]
    ).exists():
        # Never texted about this date yet: the welcome text (rendered at send
        # time) already shows the new date.
        queue_now(court_date, Kind.ENROLLMENT, now=now)
    schedule(court_date, now=now)
    return True


@transaction.atomic
def cancel(court_date: CourtDate, *, notify: bool = True, now: dt.datetime | None = None) -> None:
    now = now or timezone.now()
    court_date.status = CourtDate.Status.CANCELED
    court_date.save(update_fields=["status", "updated_at"])
    _cancel_pending(court_date, now, "Court date canceled")
    if notify and _has_been_texted(court_date) and court_date.starts_at > now:
        queue_now(court_date, Kind.CANCELED, now=now)


@transaction.atomic
def record_outcome(
    court_date: CourtDate,
    status: str,
    *,
    notify: bool | None = None,
    now: dt.datetime | None = None,
) -> None:
    """Record whether the person came to court. A miss can trigger a follow-up text."""
    if status not in (CourtDate.Status.ATTENDED, CourtDate.Status.MISSED):
        raise ValueError(f"Not an outcome: {status}")
    now = now or timezone.now()
    court_date.status = status
    court_date.save(update_fields=["status", "updated_at"])
    _cancel_pending(court_date, now, f"Marked {status}")
    if notify is None:
        notify = settings.DOCKETBELL_SEND_MISSED_FOLLOW_UP
    if status == CourtDate.Status.MISSED and notify:
        queue_now(court_date, Kind.MISSED, now=now)


def mark_confirmed(court_date: CourtDate, *, now: dt.datetime | None = None) -> None:
    now = now or timezone.now()
    court_date.confirmed_at = court_date.confirmed_at or now
    court_date.save(update_fields=["confirmed_at", "updated_at"])


def mark_needs_help(court_date: CourtDate, *, now: dt.datetime | None = None) -> None:
    court_date.needs_help_at = now or timezone.now()
    court_date.help_resolved_at = None
    court_date.save(update_fields=["needs_help_at", "help_resolved_at", "updated_at"])


def resolve_help(court_date: CourtDate, *, now: dt.datetime | None = None) -> None:
    court_date.help_resolved_at = now or timezone.now()
    court_date.save(update_fields=["help_resolved_at", "updated_at"])


# --- Sending ------------------------------------------------------------------


@dataclass
class SendOutcome:
    message: Message
    ok: bool
    retryable: bool = False


def status_callback_url(backend: BaseBackend) -> str | None:
    if not (backend.status_callback_url_name and settings.DOCKETBELL_PUBLIC_URL):
        return None
    return settings.DOCKETBELL_PUBLIC_URL + reverse(backend.status_callback_url_name)


def send_sms(
    *,
    to: str,
    body: str,
    kind: str,
    person: Person | None = None,
    court_date: CourtDate | None = None,
    language: str = "",
    sent_by=None,
    backend: BaseBackend | None = None,
    now: dt.datetime | None = None,
) -> SendOutcome:
    """Send one text and log it as a Message. Never raises for provider errors."""
    backend = backend or get_backend()
    message = Message(
        person=person,
        court_date=court_date,
        direction=Message.Direction.OUTBOUND,
        phone=to,
        body=body,
        language=language,
        kind=kind,
        backend=backend.name,
        segments=analyze(body).segments,
        sent_by=sent_by,
        created_at=now or timezone.now(),
    )
    try:
        result = backend.send(to, body, callback_url=status_callback_url(backend))
    except SMSError as exc:
        message.status = Message.Status.FAILED
        message.error = str(exc)[:300]
        message.save()
        log.warning("SMS to %s failed: %s", mask(to), exc)
        if person is not None and exc.opted_out:
            Person.objects.filter(phone=to, opted_out_at__isnull=True).update(
                opted_out_at=timezone.now()
            )
        if person is not None and exc.invalid_number:
            Person.objects.filter(phone=to).update(phone_status=Person.PhoneStatus.UNDELIVERABLE)
        return SendOutcome(message, ok=False, retryable=exc.retryable)
    message.provider_id = result.provider_id
    message.status = (
        Message.Status.DELIVERED if result.status == "delivered" else Message.Status.SENT
    )
    message.save()
    log.info("SMS %s sent to %s (%s)", kind, mask(to), result.provider_id or "no id")
    return SendOutcome(message, ok=True)


def send_to_person(
    person: Person,
    kind: str,
    *,
    court_date: CourtDate | None = None,
    language: str | None = None,
    backend: BaseBackend | None = None,
    now: dt.datetime | None = None,
) -> SendOutcome:
    """Render one of the built-in texts for a person and send it."""
    language = language or person.language
    body = copy.render_for(kind, person=person, court_date=court_date, language=language)
    return send_sms(
        to=person.phone,
        body=body,
        kind=kind,
        person=person,
        court_date=court_date,
        language=language,
        backend=backend,
        now=now,
    )


def send_manual(
    person: Person,
    body: str,
    *,
    user,
    court_date: CourtDate | None = None,
    backend: BaseBackend | None = None,
) -> SendOutcome:
    """A text typed by staff."""
    return send_sms(
        to=person.phone,
        body=body.strip(),
        kind="manual",
        person=person,
        court_date=court_date,
        language=person.language,
        sent_by=user,
        backend=backend,
    )


# --- Dispatch -----------------------------------------------------------------

REQUIRED_STATUS = {
    Kind.CANCELED: CourtDate.Status.CANCELED,
    Kind.MISSED: CourtDate.Status.MISSED,
}


def _finish(reminder: Reminder, status: str, detail: str = "") -> str:
    reminder.status = status
    reminder.detail = detail[:300]
    reminder.save(update_fields=["status", "detail", "message", "attempts", "updated_at"])
    return status


def _retry_delay(attempts: int) -> dt.timedelta:
    return dt.timedelta(minutes=5 * 2 ** max(attempts - 1, 0))


def process_reminder(reminder: Reminder, *, now: dt.datetime, backend: BaseBackend) -> str:
    """Send one due reminder, or decide why not. Returns what happened."""
    court_date = reminder.court_date
    person = court_date.person
    tz = court_date.court.tzinfo
    before_hearing = reminder.kind in Reminder.BEFORE_HEARING

    required = REQUIRED_STATUS.get(reminder.kind, CourtDate.Status.SCHEDULED)
    if court_date.status != required:
        return _finish(
            reminder,
            Reminder.Status.CANCELED,
            f"Court date is now {court_date.get_status_display().lower()}",
        )
    if before_hearing and now >= court_date.starts_at:
        return _finish(reminder, Reminder.Status.SKIPPED, "Court date already started")
    if person.is_opted_out:
        return _finish(reminder, Reminder.Status.SKIPPED, "Person opted out of texts")
    if reminder.kind in Reminder.COUNTDOWN:
        # After an outage several reminders can be due at once. Send only the latest.
        later = court_date.reminders.filter(
            status=Reminder.Status.PENDING,
            kind__in=Reminder.COUNTDOWN,
            send_at__lte=now,
            send_at__gt=reminder.send_at,
        )
        if later.exists():
            return _finish(reminder, Reminder.Status.SKIPPED, "A later reminder was due too")

    allowed = next_send_time(now, tz)
    if allowed > now:
        if before_hearing and allowed >= court_date.starts_at:
            return _finish(reminder, Reminder.Status.SKIPPED, "No time left inside the send window")
        reminder.send_at = allowed
        reminder.save(update_fields=["send_at", "updated_at"])
        return "deferred"

    outcome = send_to_person(person, reminder.kind, court_date=court_date, backend=backend, now=now)
    reminder.attempts += 1
    reminder.message = outcome.message
    if outcome.ok:
        return _finish(reminder, Reminder.Status.SENT)
    if outcome.retryable and reminder.attempts < settings.DOCKETBELL_MAX_ATTEMPTS:
        reminder.send_at = now + _retry_delay(reminder.attempts)
        reminder.detail = outcome.message.error
        reminder.save(update_fields=["send_at", "detail", "attempts", "message", "updated_at"])
        return "retrying"
    return _finish(reminder, Reminder.Status.FAILED, outcome.message.error)


def dispatch_due(
    *,
    now: dt.datetime | None = None,
    limit: int = 200,
    backend: BaseBackend | None = None,
) -> Counter:
    """Send every reminder that is due. Safe to run from several workers at once."""
    now = now or timezone.now()
    results: Counter = Counter()
    due_ids = list(
        Reminder.objects.filter(status=Reminder.Status.PENDING, send_at__lte=now)
        .order_by("send_at", "id")
        .values_list("id", flat=True)[:limit]
    )
    if not due_ids:
        return results
    own_backend = backend is None
    backend = backend or get_backend()
    try:
        for reminder_id in due_ids:
            with transaction.atomic():
                reminder = (
                    Reminder.objects.select_for_update(skip_locked=True, of=("self",))
                    .select_related("court_date__person", "court_date__court")
                    .filter(pk=reminder_id, status=Reminder.Status.PENDING, send_at__lte=now)
                    .first()
                )
                if reminder is None:
                    continue  # another worker has it, or it changed
                results[process_reminder(reminder, now=now, backend=backend)] += 1
    finally:
        if own_backend:
            backend.close()
    return results


# --- Delivery reports ---------------------------------------------------------

DELIVERY_STATUS = {
    "delivered": Message.Status.DELIVERED,
    "read": Message.Status.DELIVERED,
    "undelivered": Message.Status.UNDELIVERED,
    "failed": Message.Status.FAILED,
}


def record_delivery(
    provider_id: str,
    status: str,
    *,
    error_code: str = "",
    error: str = "",
    undeliverable_codes: frozenset[str] = frozenset(),
) -> Message | None:
    """Apply a provider's delivery report to the matching outbound message."""
    new_status = DELIVERY_STATUS.get((status or "").lower())
    if not provider_id or new_status is None:
        return None
    message = (
        Message.objects.select_related("person")
        .filter(provider_id=provider_id, direction=Message.Direction.OUTBOUND)
        .first()
    )
    if message is None:
        return None
    message.status = new_status
    if error or error_code:
        message.error = (f"{error_code} {error}".strip())[:300]
    message.save(update_fields=["status", "error"])
    if message.person_id:
        people = Person.objects.filter(phone=message.phone)
        if new_status == Message.Status.DELIVERED:
            people.update(phone_status=Person.PhoneStatus.OK)
        elif error_code in undeliverable_codes or error_code == "invalid_number":
            people.update(phone_status=Person.PhoneStatus.UNDELIVERABLE)
    return message


# --- Worker health ------------------------------------------------------------


def heartbeat(name: str = "worker", *, now: dt.datetime | None = None) -> None:
    Heartbeat.objects.update_or_create(
        name=name, defaults={"seen_at": now or timezone.now(), "version": build_info().version}
    )


def worker_status(*, now: dt.datetime | None = None, stale_after: int = 300) -> dict:
    """Whether a worker has checked in recently, for the dashboard and /healthz."""
    now = now or timezone.now()
    last = Heartbeat.objects.order_by("-seen_at").first()
    overdue = Reminder.objects.filter(
        status=Reminder.Status.PENDING, send_at__lte=now - dt.timedelta(minutes=10)
    ).count()
    healthy = last is not None and (now - last.seen_at).total_seconds() < stale_after
    return {"healthy": healthy, "last_seen": last.seen_at if last else None, "overdue": overdue}
