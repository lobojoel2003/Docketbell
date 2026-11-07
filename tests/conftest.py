from __future__ import annotations

import datetime as dt
import zoneinfo

import pytest
from django.utils import timezone

from docketbell.core.models import Court, CourtDate, Person
from docketbell.sms.backends import locmem

NY = zoneinfo.ZoneInfo("America/New_York")


def local(year, month, day, hour=0, minute=0) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, tzinfo=NY)


# A Monday morning, well inside the send window.
NOW = local(2026, 11, 2, 9, 0)


@pytest.fixture(autouse=True)
def _clean_outbox():
    locmem.outbox.clear()
    yield
    locmem.outbox.clear()


@pytest.fixture
def outbox():
    return locmem.outbox


@pytest.fixture
def now():
    return NOW


@pytest.fixture
def court(db):
    return Court.objects.create(
        name="Main Street Courthouse",
        address="100 Main St",
        timezone="America/New_York",
        phone="(212) 555-0100",
    )


@pytest.fixture
def person(db):
    return Person.objects.create(first_name="Maria", last_name="Lopez", phone="+12125550142")


@pytest.fixture
def make_court_date(court, person):
    def make(starts_at=None, **kwargs):
        kwargs.setdefault("person", person)
        kwargs.setdefault("court", court)
        kwargs.setdefault("room", "Courtroom 4B")
        return CourtDate.objects.create(starts_at=starts_at or local(2026, 11, 17, 9, 30), **kwargs)

    return make


@pytest.fixture
def court_date(make_court_date):
    return make_court_date()


@pytest.fixture
def staff(django_user_model):
    return django_user_model.objects.create_user(
        "staff", password="a-long-test-password", is_staff=True
    )


@pytest.fixture
def staff_client(client, staff):
    client.force_login(staff)
    return client


@pytest.fixture
def frozen(time_machine):
    """Freeze the clock at NOW for code paths that call timezone.now()."""
    time_machine.move_to(NOW, tick=False)
    assert timezone.now() == NOW
    return NOW
