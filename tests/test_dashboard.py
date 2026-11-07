from __future__ import annotations

import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from docketbell.core import services
from docketbell.core.models import Court, CourtDate, Message, MessageTemplate, Person, Reminder
from tests.conftest import NOW, local

PAGES = [
    "dashboard:home",
    "dashboard:court-dates",
    "dashboard:people",
    "dashboard:inbox",
    "dashboard:studio",
    "dashboard:results",
    "dashboard:import",
    "dashboard:court-date-new",
]


@pytest.mark.parametrize("name", PAGES)
def test_pages_require_login(client, db, name):
    response = client.get(reverse(name))
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("login"))


@pytest.mark.parametrize("name", PAGES)
def test_pages_render(staff_client, court_date, frozen, name):
    services.enroll(court_date, now=NOW)
    services.dispatch_due(now=NOW)
    response = staff_client.get(reverse(name))
    assert response.status_code == 200


def test_login_page(client, db):
    response = client.get(reverse("login"))
    assert response.status_code == 200
    assert b"Docketbell" in response.content


def test_home_shows_who_confirmed(staff_client, make_court_date, frozen):
    confirmed = make_court_date(NOW + dt.timedelta(days=1))
    other = Person.objects.create(first_name="Wei", last_name="Chen", phone="+12125550143")
    make_court_date(NOW + dt.timedelta(days=2), person=other)
    services.mark_confirmed(confirmed, now=NOW)
    response = staff_client.get(reverse("dashboard:home"))
    assert response.context["total"] == 2
    breakdown = {b["key"]: b["count"] for b in response.context["breakdown"]}
    assert breakdown == {"confirmed": 1, "needs_help": 0, "no_reply": 1, "unreachable": 0}
    assert response.context["confirmed"]["share"] == 50
    content = response.content.decode()
    assert "Maria Lopez" in content and "Wei Chen" in content and "50%" in content

    only = staff_client.get(reverse("dashboard:home") + "?response=confirmed&days=7")
    names = [cd.person.first_name for _, _, items in only.context["groups"] for cd in items]
    assert names == ["Maria"]


def test_home_court_filter_and_bad_range(staff_client, make_court_date, frozen):
    court_date = make_court_date(NOW + dt.timedelta(days=3))
    response = staff_client.get(reverse("dashboard:home") + f"?court={court_date.court_id}&days=x")
    assert response.context["days"] == 14
    assert response.context["total"] == 1
    response = staff_client.get(reverse("dashboard:home") + f"?court={court_date.court_id + 1}")
    assert response.context["total"] == 0


def test_home_lists_people_who_need_help(staff_client, make_court_date, frozen):
    court_date = make_court_date(NOW + dt.timedelta(days=2))
    services.mark_needs_help(court_date, now=NOW)
    response = staff_client.get(reverse("dashboard:home"))
    assert response.context["needs_help"] == [court_date]
    assert "asked for help" in response.content.decode()


def test_worker_warning_banner(staff_client, court_date, frozen):
    services.queue_now(court_date, Reminder.Kind.ENROLLMENT, now=NOW - dt.timedelta(hours=1))
    response = staff_client.get(reverse("dashboard:home"))
    assert "Reminders are not going out" in response.content.decode()
    services.heartbeat(now=NOW)
    response = staff_client.get(reverse("dashboard:home"))
    assert "Reminders are not going out" not in response.content.decode()


def test_create_court_date(staff_client, court, frozen, outbox):
    response = staff_client.post(
        reverse("dashboard:court-date-new"),
        {
            "first_name": "Ana",
            "last_name": "Diaz",
            "phone": "(212) 555-0177",
            "language": "es",
            "consent": "on",
            "court": court.pk,
            "date": "2026-11-20",
            "time": "09:30",
            "room": "4B",
            "hearing_type": "",
            "case_number": "",
        },
    )
    court_date = CourtDate.objects.get()
    assert response.status_code == 302
    assert response["Location"] == reverse("dashboard:court-date", args=[court_date.pk])
    assert court_date.person.phone == "+12125550177"
    assert court_date.starts_at == local(2026, 11, 20, 9, 30)
    assert court_date.reminders.count() == 4
    services.dispatch_due(now=NOW)
    assert "20 de noviembre" in outbox[0].body


def test_create_requires_consent_valid_phone_and_future_date(staff_client, court, frozen):
    response = staff_client.post(
        reverse("dashboard:court-date-new"),
        {
            "first_name": "Ana",
            "phone": "123",
            "language": "en",
            "court": court.pk,
            "date": "2026-10-01",
            "time": "09:30",
        },
    )
    form = response.context["form"]
    assert set(form.errors) == {"phone", "consent", "__all__"}
    assert not CourtDate.objects.exists()


def test_create_for_existing_person(staff_client, person, court, frozen):
    url = reverse("dashboard:court-date-new") + f"?person={person.pk}"
    staff_client.post(url, {"court": court.pk, "date": "2026-12-01", "time": "10:00"})
    assert person.court_dates.count() == 1


def test_create_reuses_matching_person(staff_client, person, court, frozen):
    staff_client.post(
        reverse("dashboard:court-date-new"),
        {
            "first_name": "maria",
            "phone": person.phone,
            "language": "vi",
            "consent": "on",
            "court": court.pk,
            "date": "2026-12-01",
            "time": "10:00",
        },
    )
    person.refresh_from_db()
    assert Person.objects.count() == 1 and person.language == "vi"


def test_create_without_courts_redirects_to_admin(staff_client, db):
    response = staff_client.get(reverse("dashboard:court-date-new"))
    assert response["Location"] == reverse("admin:core_court_add")


def test_detail_shows_conversation(staff_client, court_date, frozen):
    services.enroll(court_date, now=NOW)
    services.dispatch_due(now=NOW)
    response = staff_client.get(reverse("dashboard:court-date", args=[court_date.pk]))
    content = response.content.decode()
    assert "this is Main Street Defenders" in content
    assert "Heads-up" in content and "Training mode" in content


def test_edit_reschedules(staff_client, court_date, frozen):
    services.enroll(court_date, now=NOW)
    url = reverse("dashboard:court-date-edit", args=[court_date.pk])
    assert staff_client.get(url).status_code == 200
    staff_client.post(
        url,
        {
            "court": court_date.court_id,
            "date": "2026-11-19",
            "time": "11:00",
            "room": "5",
            "notify": "on",
        },
    )
    court_date.refresh_from_db()
    assert court_date.starts_at == local(2026, 11, 19, 11)
    assert court_date.room == "5"


@pytest.mark.parametrize(
    ("action", "field", "value"),
    [
        ("confirm", "confirmed_at", True),
        ("attended", "status", "attended"),
        ("missed", "status", "missed"),
        ("cancel", "status", "canceled"),
    ],
)
def test_actions(staff_client, court_date, frozen, action, field, value):
    staff_client.post(
        reverse("dashboard:court-date-action", args=[court_date.pk]),
        {"action": action, "notify": "on"},
    )
    court_date.refresh_from_db()
    actual = getattr(court_date, field)
    assert (actual is not None) if value is True else actual == value


def test_unconfirm_and_resolve_help(staff_client, court_date, frozen):
    services.mark_confirmed(court_date)
    services.mark_needs_help(court_date)
    url = reverse("dashboard:court-date-action", args=[court_date.pk])
    staff_client.post(url, {"action": "unconfirm"})
    staff_client.post(url, {"action": "resolve_help"})
    court_date.refresh_from_db()
    assert court_date.confirmed_at is None and not court_date.needs_help
    assert staff_client.post(url, {"action": "explode"}).status_code == 404


def test_manual_text(staff_client, court_date, staff, outbox):
    url = reverse("dashboard:court-date-text", args=[court_date.pk])
    staff_client.post(url, {"body": "  Please call us back today.  "})
    message = Message.objects.get()
    assert message.sent_by == staff and message.kind == "manual"
    assert outbox[0].body == "Please call us back today."
    staff_client.post(url, {"body": ""})
    Person.objects.update(opted_out_at=NOW)
    staff_client.post(url, {"body": "Hello"})
    assert len(outbox) == 1


def test_simulated_reply(staff_client, court_date, settings, outbox):
    url = reverse("dashboard:court-date-simulate", args=[court_date.pk])
    staff_client.post(url, {"body": "1"})
    court_date.refresh_from_db()
    assert court_date.confirmed_at is not None
    settings.DOCKETBELL_ALLOW_SIMULATED_REPLIES = False
    assert staff_client.post(url, {"body": "1"}).status_code == 404


def test_lists_and_search(staff_client, court_date, frozen):
    court_dates = reverse("dashboard:court-dates")
    assert staff_client.get(court_dates + "?q=lopez").context["page"].paginator.count == 1
    assert staff_client.get(court_dates + "?q=0142").context["page"].paginator.count == 1
    assert staff_client.get(court_dates + "?when=past").context["page"].paginator.count == 0
    assert staff_client.get(court_dates + "?status=missed").context["page"].paginator.count == 0
    people = reverse("dashboard:people")
    response = staff_client.get(people + "?q=555-0142")
    assert list(response.context["page"]) == [court_date.person]
    assert response.context["page"][0].next_date == court_date


def test_person_edit(staff_client, person):
    url = reverse("dashboard:person", args=[person.pk])
    Person.objects.filter(pk=person.pk).update(phone_status="undeliverable")
    staff_client.post(
        url,
        {
            "first_name": "María",
            "last_name": "López",
            "phone": "212-555-0144",
            "language": "es",
            "notes": "",
        },
    )
    person.refresh_from_db()
    assert person.phone == "+12125550144" and person.phone_status == "ok"


def test_inbox(staff_client, court_date, frozen):
    from docketbell.core import replies

    message = replies.handle_inbound(
        phone=court_date.person.phone, body="What do I bring?", now=NOW
    )
    response = staff_client.get(reverse("dashboard:inbox"))
    assert list(response.context["page"]) == [message]
    staff_client.post(reverse("dashboard:inbox-handle", args=[message.pk]), {})
    assert list(staff_client.get(reverse("dashboard:inbox")).context["page"]) == []
    assert len(staff_client.get(reverse("dashboard:inbox") + "?show=all").context["page"]) == 1


@pytest.mark.parametrize("language", ["en", "es", "zh-hans", "ar", "ht", "nope"])
def test_studio(staff_client, db, language):
    response = staff_client.get(reverse("dashboard:studio") + f"?lang={language}")
    assert response.status_code == 200
    assert response.context["typical_texts"] == 4
    assert response.context["direction"] == ("rtl" if language == "ar" else "ltr")


def test_studio_marks_custom_texts(staff_client, db):
    MessageTemplate.objects.create(kind="tomorrow", language="en", body="Court tomorrow {time}")
    response = staff_client.get(reverse("dashboard:studio"))
    custom = [i for i in response.context["groups"]["reminder"] if i["custom"]]
    assert [i["spec"].kind for i in custom] == ["tomorrow"]


def test_results(staff_client, make_court_date, frozen):
    past = [make_court_date(NOW - dt.timedelta(days=d)) for d in (3, 4, 5, 6)]
    services.mark_confirmed(past[0])
    for court_date in past[:3]:
        services.record_outcome(court_date, CourtDate.Status.ATTENDED, notify=False)
    services.record_outcome(past[3], CourtDate.Status.MISSED, notify=False)
    response = staff_client.get(reverse("dashboard:results") + "?days=30")
    assert response.context["overall"] == {"total": 4, "attended": 3, "rate": 75}
    groups = {g["label"]: g["rate"] for g in response.context["groups"]}
    assert groups == {"Confirmed by text": 100, "Asked for help": None, "Never replied": 67}
    assert staff_client.get(reverse("dashboard:results") + "?days=bad").context["days"] == 90


def test_import_upload(staff_client, court, frozen):
    csv = (
        b"first_name,phone,court,date,time\n"
        b"Maria,2125550142,Main Street Courthouse,2026-11-20,09:30\n"
    )
    url = reverse("dashboard:import")
    response = staff_client.post(url, {"file": SimpleUploadedFile("a.csv", csv), "dry_run": "on"})
    assert response.context["report"].created == 1 and not CourtDate.objects.exists()
    response = staff_client.post(url, {"file": SimpleUploadedFile("a.csv", csv)})
    assert CourtDate.objects.count() == 1
    bad = SimpleUploadedFile("a.csv", b"\xff\xfe\x00bad")
    response = staff_client.post(url, {"file": bad})
    assert "file" in response.context["form"].errors


def test_import_template(staff_client, db):
    response = staff_client.get(reverse("dashboard:import-template"))
    assert response["Content-Type"].startswith("text/csv")
    assert b"first_name" in response.content


def test_ui_in_spanish(staff_client, court_date, frozen):
    response = staff_client.get(reverse("dashboard:home"), HTTP_ACCEPT_LANGUAGE="es")
    assert response.status_code == 200
    assert '<html lang="es"' in response.content.decode()


def test_admin_pages(staff, client, court_date):
    staff.is_superuser = True
    staff.save()
    client.force_login(staff)
    for model in (
        "court",
        "person",
        "courtdate",
        "reminder",
        "message",
        "messagetemplate",
        "heartbeat",
    ):
        assert client.get(reverse(f"admin:core_{model}_changelist")).status_code == 200
    assert client.get(reverse("admin:core_messagetemplate_add")).status_code == 200


def test_admin_creates_and_moves_court_dates(staff, client, court, person, frozen):
    staff.is_superuser = True
    staff.save()
    client.force_login(staff)
    add = reverse("admin:core_courtdate_add")
    data = {
        "person": person.pk,
        "court": court.pk,
        "starts_at_0": "2026-11-20",
        "starts_at_1": "09:30",
        "room": "",
        "hearing_type": "",
        "case_number": "",
        "status": "scheduled",
        "external_id": "",
        "reminders-TOTAL_FORMS": 0,
        "reminders-INITIAL_FORMS": 0,
    }
    assert client.post(add, data).status_code == 302
    court_date = CourtDate.objects.get()
    assert court_date.reminders.count() == 4
    data["starts_at_1"] = "11:00"
    change = reverse("admin:core_courtdate_change", args=[court_date.pk])
    assert client.post(change, data).status_code == 302
    court_date.refresh_from_db()
    assert court_date.starts_at.astimezone(court.tzinfo).hour == 11


def test_court_time_zone_is_validated(court):
    from django.core.exceptions import ValidationError

    assert str(court) == "Main Street Courthouse"
    with pytest.raises(ValidationError):
        Court(name="Moon Court", timezone="Mars/Base").full_clean()
