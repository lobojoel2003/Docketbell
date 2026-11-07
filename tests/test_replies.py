from __future__ import annotations

import datetime as dt

import pytest

from docketbell.core import replies, services
from docketbell.core.models import Message, Person
from tests.conftest import NOW

Intent = Message.Intent


@pytest.mark.parametrize(
    ("body", "intent"),
    [
        ("1", Intent.CONFIRM),
        (" 1. ", Intent.CONFIRM),
        ("Yes!", Intent.CONFIRM),
        ("yes I'll be there", Intent.CONFIRM),
        ("sí", Intent.CONFIRM),
        ("Si", Intent.CONFIRM),
        ("Có", Intent.CONFIRM),
        ("vâng", Intent.CONFIRM),
        ("да", Intent.CONFIRM),
        ("네", Intent.CONFIRM),
        ("نعم", Intent.CONFIRM),
        ("Wi", Intent.CONFIRM),
        ("好的", Intent.CONFIRM),
        ("是的，我会去", Intent.CONFIRM),
        ("2", Intent.NEEDS_HELP),
        ("No", Intent.NEEDS_HELP),
        ("no I can't", Intent.NEEDS_HELP),
        ("Can't make it", Intent.NEEDS_HELP),
        ("no puedo ir", Intent.NEEDS_HELP),
        ("不能去", Intent.NEEDS_HELP),
        ("нет", Intent.NEEDS_HELP),
        ("pa kapab", Intent.NEEDS_HELP),
        ("STOP", Intent.STOP),
        ("Stop.", Intent.STOP),
        ("stop texting me", Intent.STOP),
        ("UNSUBSCRIBE", Intent.STOP),
        ("cancel", Intent.STOP),
        ("ALTO", Intent.STOP),
        ("START", Intent.START),
        ("unstop", Intent.START),
        ("HELP", Intent.INFO),
        ("info", Intent.INFO),
        ("ayuda", Intent.INFO),
        ("What should I bring?", Intent.UNKNOWN),
        ("", Intent.UNKNOWN),
        ("🙂", Intent.UNKNOWN),
        ("对不起", Intent.UNKNOWN),
        ("cancel my court date please", Intent.UNKNOWN),
    ],
)
def test_classify(body, intent):
    assert replies.classify(body)[0] == intent


@pytest.mark.parametrize(
    ("body", "language"),
    [
        ("Español", "es"),
        ("espanol", "es"),
        ("SPANISH", "es"),
        ("中文", "zh-hans"),
        ("tieng viet", "vi"),
        ("Tiếng Việt", "vi"),
        ("한국어", "ko"),
        ("Русский", "ru"),
        ("العربية", "ar"),
        ("Kreyòl", "ht"),
        ("english", "en"),
    ],
)
def test_language_names(body, language):
    assert replies.classify(body) == (Intent.LANGUAGE, language)


def inbound(body, phone="+12125550142", **kwargs):
    return replies.handle_inbound(phone=phone, body=body, now=kwargs.pop("now", NOW), **kwargs)


def test_confirm(court_date, outbox):
    message = inbound("1", provider_id="SM1")
    court_date.refresh_from_db()
    assert court_date.confirmed_at == NOW
    assert court_date.response == "confirmed"
    assert message.intent == Intent.CONFIRM and message.court_date == court_date
    assert outbox[-1].body.startswith("Thank you, Maria. You're confirmed for Tuesday")


def test_phone_numbers_are_normalized(court_date):
    inbound("yes", phone="(212) 555-0142")
    court_date.refresh_from_db()
    assert court_date.confirmed_at is not None


def test_needs_help_flags_for_staff(court_date, outbox):
    message = inbound("2")
    court_date.refresh_from_db()
    assert court_date.needs_help and court_date.response == "needs_help"
    assert message.needs_attention
    assert "Someone from Main Street Defenders will contact you soon" in outbox[-1].body


def test_stop_and_start(court_date, outbox):
    inbound("STOP")
    court_date.person.refresh_from_db()
    assert court_date.person.is_opted_out
    assert "Reply START" in outbox[-1].body
    inbound("START")
    court_date.person.refresh_from_db()
    assert not court_date.person.is_opted_out
    assert "again" in outbox[-1].body


def test_stop_confirmation_can_be_turned_off(settings, court_date, outbox):
    settings.DOCKETBELL_SEND_OPT_OUT_CONFIRMATION = False
    inbound("STOP")
    assert outbox == []


def test_opted_out_people_get_no_replies_but_staff_see_them(court_date, outbox):
    Person.objects.update(opted_out_at=NOW)
    message = inbound("Can I come at noon instead?")
    assert outbox == []
    assert message.needs_attention
    inbound("1")
    court_date.refresh_from_db()
    assert court_date.confirmed_at is not None
    assert outbox == []
    inbound("2")
    court_date.refresh_from_db()
    assert court_date.needs_help


def test_info(court_date, outbox):
    inbound("HELP")
    assert "Msg & data rates may apply" in outbox[-1].body


def test_language_switch_replies_in_new_language(court_date, outbox):
    inbound("Español")
    court_date.person.refresh_from_db()
    assert court_date.person.language == "es"
    assert "español" in outbox[-1].body


def test_unknown_reply_is_answered_once_a_day(court_date, outbox):
    first = inbound("What should I bring?")
    inbound("Hello?", now=NOW + dt.timedelta(hours=1))
    assert first.needs_attention
    assert len(outbox) == 1 and "couldn't read that" in outbox[0].body
    inbound("Anyone?", now=NOW + dt.timedelta(hours=25))
    assert len(outbox) == 2


def test_confirm_without_upcoming_court_date(person, outbox):
    inbound("1")
    assert "don't see an upcoming court date" in outbox[-1].body


def test_unknown_numbers_are_never_answered(db, outbox):
    message = inbound("1", phone="+12125550111")
    assert message.person is None and message.needs_attention
    assert outbox == []


def test_unknown_number_stop_is_recorded(db, outbox):
    message = inbound("STOP", phone="+12125550111")
    assert message.intent == Intent.STOP
    assert outbox == []


def test_provider_retries_are_handled_once(court_date, outbox):
    first = inbound("1", provider_id="SM-dup")
    second = inbound("1", provider_id="SM-dup")
    assert first.pk == second.pk
    assert Message.objects.filter(direction="in").count() == 1
    assert len(outbox) == 1


def test_reply_applies_to_the_next_court_date(make_court_date, outbox):
    later = make_court_date(NOW + dt.timedelta(days=30))
    sooner = make_court_date(NOW + dt.timedelta(days=3))
    inbound("1")
    sooner.refresh_from_db()
    later.refresh_from_db()
    assert sooner.confirmed_at and not later.confirmed_at


def test_shared_phone_matches_person_with_next_date(court, person, make_court_date):
    sibling = Person.objects.create(first_name="Ana", phone=person.phone)
    target = make_court_date(NOW + dt.timedelta(days=2), person=sibling)
    make_court_date(NOW + dt.timedelta(days=9))
    message = inbound("1")
    assert message.person == sibling and message.court_date == target
    services.dispatch_due(now=NOW)
