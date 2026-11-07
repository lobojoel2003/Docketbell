from __future__ import annotations

import datetime as dt

import pytest

from docketbell.core import services
from docketbell.core.models import CourtDate, Message, Reminder
from docketbell.sms import SMSError
from docketbell.sms.backends.base import BaseBackend, SendResult
from tests.conftest import NOW, local

Kind = Reminder.Kind
Status = Reminder.Status


def plan(court_date, now=NOW):
    return [
        (kind, when.astimezone(court_date.court.tzinfo))
        for kind, when in services.plan_reminders(court_date, now)
    ]


def test_default_plan_is_week_three_days_and_day_before(court_date):
    assert plan(court_date) == [
        (Kind.HEADS_UP, local(2026, 11, 10, 10)),
        (Kind.PLAN, local(2026, 11, 14, 10)),
        (Kind.TOMORROW, local(2026, 11, 16, 10)),
    ]


def test_late_signup_skips_past_reminders_and_keeps_the_heads_up(make_court_date):
    court_date = make_court_date(local(2026, 11, 6, 9, 30))
    assert plan(court_date) == [
        (Kind.HEADS_UP, local(2026, 11, 3, 10)),
        (Kind.TOMORROW, local(2026, 11, 5, 10)),
    ]


def test_morning_of_reminder(settings, court_date):
    settings.DOCKETBELL_REMINDER_DAYS = [2, 0]
    assert plan(court_date) == [
        (Kind.HEADS_UP, local(2026, 11, 15, 10)),
        (Kind.TODAY, local(2026, 11, 17, 8)),
    ]


def test_morning_of_skipped_for_early_hearings(settings, make_court_date):
    settings.DOCKETBELL_REMINDER_DAYS = [0]
    assert plan(make_court_date(local(2026, 11, 17, 8, 30))) == []


def test_plan_across_daylight_saving_change(make_court_date):
    # DST ended on Nov 1, 2026: the 7-day reminder is still sent at 10:00 local.
    court_date = make_court_date(local(2026, 11, 4, 9))
    assert plan(court_date, now=local(2026, 10, 25, 9)) == [
        (Kind.HEADS_UP, local(2026, 10, 28, 10)),
        (Kind.PLAN, local(2026, 11, 1, 10)),
        (Kind.TOMORROW, local(2026, 11, 3, 10)),
    ]


def test_countdown_schedule(settings):
    settings.DOCKETBELL_REMINDER_DAYS = [1, 7, 3, 14, 0]
    assert services.countdown_schedule() == [
        (Kind.HEADS_UP, 14),
        (Kind.PLAN, 7),
        (Kind.PLAN, 3),
        (Kind.TOMORROW, 1),
        (Kind.TODAY, 0),
    ]


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (local(2026, 11, 2, 7, 59), local(2026, 11, 2, 8)),
        (local(2026, 11, 2, 8), local(2026, 11, 2, 8)),
        (local(2026, 11, 2, 19, 59), local(2026, 11, 2, 19, 59)),
        (local(2026, 11, 2, 20), local(2026, 11, 3, 8)),
        (local(2026, 11, 2, 23, 30), local(2026, 11, 3, 8)),
    ],
)
def test_send_window(moment, expected, court):
    assert services.next_send_time(moment, court.tzinfo) == expected


def test_enroll_queues_welcome_and_countdown(court_date):
    services.enroll(court_date, now=NOW)
    kinds = list(court_date.reminders.values_list("kind", "status"))
    assert kinds == [
        (Kind.ENROLLMENT, Status.PENDING),
        (Kind.HEADS_UP, Status.PENDING),
        (Kind.PLAN, Status.PENDING),
        (Kind.TOMORROW, Status.PENDING),
    ]


def test_enroll_ignores_past_dates(make_court_date):
    court_date = make_court_date(local(2026, 11, 1, 9))
    services.enroll(court_date, now=NOW)
    assert not court_date.reminders.exists()


def test_enroll_at_night_waits_for_morning(court_date):
    services.enroll(court_date, now=local(2026, 11, 2, 22, 15))
    welcome = court_date.reminders.get(kind=Kind.ENROLLMENT)
    assert welcome.send_at == local(2026, 11, 3, 8)


def test_reschedule_before_any_text_just_rebuilds(court_date):
    services.enroll(court_date, now=NOW)
    moved = services.reschedule(court_date, local(2026, 11, 24, 13), now=NOW)
    assert moved is True
    pending = court_date.reminders.filter(status=Status.PENDING)
    assert list(pending.values_list("kind", flat=True)) == [
        Kind.ENROLLMENT,
        Kind.HEADS_UP,
        Kind.PLAN,
        Kind.TOMORROW,
    ]
    assert pending.get(kind=Kind.TOMORROW).send_at == local(2026, 11, 23, 10)
    assert not court_date.reminders.filter(kind=Kind.RESCHEDULED).exists()


def test_reschedule_after_texting_sends_notice_and_resets_confirmation(court_date, outbox):
    services.enroll(court_date, now=NOW)
    services.dispatch_due(now=NOW)
    services.mark_confirmed(court_date, now=NOW)
    services.reschedule(court_date, local(2026, 11, 24, 13), now=NOW)
    court_date.refresh_from_db()
    assert court_date.confirmed_at is None
    assert court_date.reminders.filter(kind=Kind.RESCHEDULED, status=Status.PENDING).exists()
    services.dispatch_due(now=NOW)
    assert "has changed" in outbox[-1].body
    assert "Tuesday, November 24 at 1:00 PM" in outbox[-1].body


def test_reschedule_same_time_is_a_no_op(court_date):
    assert services.reschedule(court_date, court_date.starts_at, now=NOW) is False


def test_reschedule_into_the_past_cancels_reminders(court_date):
    services.enroll(court_date, now=NOW)
    services.reschedule(court_date, local(2026, 11, 1, 9), now=NOW)
    assert not court_date.reminders.filter(status=Status.PENDING).exists()


def test_cancel_notifies_only_people_who_were_texted(court_date, outbox):
    services.enroll(court_date, now=NOW)
    services.cancel(court_date, now=NOW)
    assert court_date.status == CourtDate.Status.CANCELED
    assert not court_date.reminders.filter(status=Status.PENDING).exists()
    assert not court_date.reminders.filter(kind=Kind.CANCELED).exists()


def test_cancel_after_texting(court_date, outbox):
    services.enroll(court_date, now=NOW)
    services.dispatch_due(now=NOW)
    services.cancel(court_date, now=NOW)
    services.dispatch_due(now=NOW)
    assert "was canceled" in outbox[-1].body


def test_missed_court_follow_up(court_date, outbox):
    after = court_date.starts_at + dt.timedelta(hours=3)
    services.record_outcome(court_date, CourtDate.Status.MISSED, now=after)
    services.dispatch_due(now=after)
    assert "may have missed court" in outbox[-1].body


def test_missed_follow_up_can_be_turned_off(settings, court_date):
    settings.DOCKETBELL_SEND_MISSED_FOLLOW_UP = False
    services.record_outcome(court_date, CourtDate.Status.MISSED, now=NOW)
    assert not court_date.reminders.filter(kind=Kind.MISSED).exists()


def test_record_outcome_rejects_other_statuses(court_date):
    with pytest.raises(ValueError, match="Not an outcome"):
        services.record_outcome(court_date, CourtDate.Status.CANCELED)


def test_help_flags(court_date):
    services.mark_needs_help(court_date, now=NOW)
    assert court_date.needs_help
    services.resolve_help(court_date, now=NOW)
    assert not court_date.needs_help


# --- Dispatch -----------------------------------------------------------------


def test_dispatch_sends_due_reminders_once(court_date, outbox):
    services.enroll(court_date, now=NOW)
    results = services.dispatch_due(now=NOW)
    assert results == {"sent": 1}
    assert len(outbox) == 1
    assert outbox[0].to == "+12125550142"
    assert outbox[0].body.startswith("Hi Maria, this is Main Street Defenders.")
    assert services.dispatch_due(now=NOW) == {}

    message = Message.objects.get()
    assert message.kind == Kind.ENROLLMENT
    assert message.status == Message.Status.SENT
    assert message.segments == 2
    assert court_date.reminders.get(kind=Kind.ENROLLMENT).message == message


def test_full_countdown(court_date, outbox):
    services.enroll(court_date, now=NOW)
    for day in (NOW, local(2026, 11, 10, 10), local(2026, 11, 14, 10), local(2026, 11, 16, 10)):
        services.dispatch_due(now=day)
    assert [text.body.split(",")[0] for text in outbox] == [
        "Hi Maria",
        "Maria",
        "Maria",
        "Reminder: your court date is tomorrow",
    ]


def test_texts_go_out_in_the_persons_language(court_date, outbox):
    court_date.person.language = "es"
    court_date.person.save()
    services.enroll(court_date, now=NOW)
    services.dispatch_due(now=NOW)
    assert "17 de noviembre" in outbox[0].body
    assert Message.objects.get().language == "es"


def test_dispatch_skips_opted_out(court_date, outbox):
    services.enroll(court_date, now=NOW)
    court_date.person.opted_out_at = NOW
    court_date.person.save()
    assert services.dispatch_due(now=NOW) == {"skipped": 1}
    assert outbox == []


def test_dispatch_cancels_reminders_for_canceled_dates(court_date):
    services.enroll(court_date, now=NOW)
    CourtDate.objects.filter(pk=court_date.pk).update(status=CourtDate.Status.CANCELED)
    assert services.dispatch_due(now=NOW) == {"canceled": 1}


def test_dispatch_after_outage_sends_only_the_latest(court_date, outbox):
    services.enroll(court_date, now=NOW)
    services.dispatch_due(now=NOW)
    late = local(2026, 11, 16, 11)
    results = services.dispatch_due(now=late)
    assert results == {"skipped": 2, "sent": 1}
    assert "tomorrow" in outbox[-1].body


def test_dispatch_skips_reminders_after_the_hearing(court_date, outbox):
    services.enroll(court_date, now=NOW)
    results = services.dispatch_due(now=court_date.starts_at + dt.timedelta(minutes=1))
    assert results["sent"] == 0 and results["skipped"] >= 1


def test_dispatch_defers_outside_the_window(court_date, outbox):
    reminder = services.queue_now(court_date, Kind.ENROLLMENT, now=NOW)
    night = local(2026, 11, 2, 21)
    Reminder.objects.filter(pk=reminder.pk).update(send_at=night)
    assert services.dispatch_due(now=night) == {"deferred": 1}
    reminder.refresh_from_db()
    assert reminder.send_at == local(2026, 11, 3, 8)
    assert outbox == []


class FlakyBackend(BaseBackend):
    name = "flaky"

    def __init__(self, error: SMSError, **options):
        super().__init__(**options)
        self.error = error
        self.calls = 0

    def send(self, to, body, *, callback_url=None):
        self.calls += 1
        raise self.error


def test_retryable_errors_retry_with_backoff_then_fail(court_date):
    reminder = services.queue_now(court_date, Kind.ENROLLMENT, now=NOW)
    backend = FlakyBackend(SMSError("timeout", retryable=True))
    assert services.dispatch_due(now=NOW, backend=backend) == {"retrying": 1}
    reminder.refresh_from_db()
    assert reminder.send_at == NOW + dt.timedelta(minutes=5)
    assert reminder.attempts == 1

    services.dispatch_due(now=reminder.send_at, backend=backend)
    reminder.refresh_from_db()
    assert reminder.send_at == NOW + dt.timedelta(minutes=15)

    services.dispatch_due(now=reminder.send_at, backend=backend)
    reminder.refresh_from_db()
    assert reminder.status == Status.FAILED
    assert reminder.attempts == 3
    assert Message.objects.filter(status=Message.Status.FAILED).count() == 3


def test_permanent_errors_fail_immediately_and_update_the_person(court_date):
    services.queue_now(court_date, Kind.ENROLLMENT, now=NOW)
    backend = FlakyBackend(SMSError("unsubscribed", code="21610", opted_out=True))
    assert services.dispatch_due(now=NOW, backend=backend) == {"failed": 1}
    court_date.person.refresh_from_db()
    assert court_date.person.is_opted_out


def test_invalid_numbers_are_marked_undeliverable(court_date):
    services.queue_now(court_date, Kind.ENROLLMENT, now=NOW)
    backend = FlakyBackend(SMSError("landline", code="21614", invalid_number=True))
    services.dispatch_due(now=NOW, backend=backend)
    court_date.person.refresh_from_db()
    assert court_date.person.phone_status == "undeliverable"
    assert court_date.response == "unreachable"


class DeliveredBackend(BaseBackend):
    name = "delivered"
    status_callback_url_name = "sms:gateway-status"

    def __init__(self, **options):
        super().__init__(**options)
        self.callbacks = []

    def send(self, to, body, *, callback_url=None):
        self.callbacks.append(callback_url)
        return SendResult(provider_id="abc", status="delivered")


def test_status_callback_url_and_delivered_status(court_date):
    backend = DeliveredBackend()
    outcome = services.send_to_person(
        court_date.person, Kind.TOMORROW, court_date=court_date, backend=backend
    )
    assert outcome.ok
    assert outcome.message.status == Message.Status.DELIVERED
    assert backend.callbacks == ["https://reminders.example.org/sms/gateway/status/"]


def test_record_delivery(court_date):
    outcome = services.send_to_person(court_date.person, Kind.TOMORROW, court_date=court_date)
    pid = outcome.message.provider_id
    assert services.record_delivery(pid, "delivered").status == Message.Status.DELIVERED
    message = services.record_delivery(
        pid, "undelivered", error_code="30006", undeliverable_codes=frozenset({"30006"})
    )
    assert message.status == Message.Status.UNDELIVERED
    court_date.person.refresh_from_db()
    assert court_date.person.phone_status == "undeliverable"
    assert services.record_delivery(pid, "queued") is None
    assert services.record_delivery("unknown", "delivered") is None


def test_heartbeat_and_worker_status(db):
    status = services.worker_status(now=NOW)
    assert status["healthy"] is False and status["last_seen"] is None
    services.heartbeat("worker", now=NOW)
    assert services.worker_status(now=NOW + dt.timedelta(minutes=1))["healthy"] is True
    assert services.worker_status(now=NOW + dt.timedelta(minutes=10))["healthy"] is False
