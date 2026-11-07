"""Management commands, health endpoints, version info and startup checks."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone

from docketbell import __version__
from docketbell.__main__ import main
from docketbell.core import checks, services
from docketbell.core.models import CourtDate, Heartbeat, Message, Person, Reminder
from docketbell.version import BuildInfo, build_info
from tests.conftest import NOW


def test_send_due_reminders(court_date, outbox, frozen, capsys):
    services.enroll(court_date, now=NOW)
    call_command("send_due_reminders")
    assert "sent: 1" in capsys.readouterr().out
    assert Heartbeat.objects.filter(name="cron").exists()
    call_command("send_due_reminders")
    assert "nothing due" in capsys.readouterr().out


def test_run_worker_once(court_date, outbox, frozen):
    services.enroll(court_date, now=NOW)
    call_command("run_worker", "--once", "--name", "test-worker")
    assert len(outbox) == 1
    assert Heartbeat.objects.get(name="test-worker").seen_at == NOW


def test_run_worker_survives_errors(db, monkeypatch, frozen):
    def boom(**kwargs):
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(services, "dispatch_due", boom)
    call_command("run_worker", "--once")  # logs, does not raise


def test_purge_old_data(court_date, person, frozen, capsys):
    old = court_date.starts_at - dt.timedelta(days=400)
    CourtDate.objects.filter(pk=court_date.pk).update(starts_at=old)
    Person.objects.filter(pk=person.pk).update(created_at=old)
    Message.objects.create(
        person=person, direction="out", phone=person.phone, body="x", status="sent", created_at=old
    )
    quitter = Person.objects.create(first_name="Sam", phone="+12125550160", opted_out_at=old)
    Person.objects.filter(pk=quitter.pk).update(created_at=old)

    call_command("purge_old_data", "--days", "365", "--dry-run")
    assert CourtDate.objects.exists()
    call_command("purge_old_data", "--days", "365")
    out = capsys.readouterr().out
    assert "Deleted 1 court dates, 1 texts and 1 records of people" in out
    quitter.refresh_from_db()
    assert quitter.first_name == "" and quitter.is_opted_out
    assert quitter.full_name == "Name removed"
    assert not Person.objects.filter(pk=person.pk).exists()
    with pytest.raises(CommandError):
        call_command("purge_old_data", "--days", "0")


def test_seed_demo(db, capsys):
    call_command("seed_demo", "--user", "demo", "--password", "demo-password-123")
    assert CourtDate.objects.count() > 100
    assert Message.objects.filter(direction="in").exists()
    assert Reminder.objects.filter(status="sent").exists()
    assert CourtDate.objects.exclude(confirmed_at=None).exists()
    call_command("seed_demo")
    assert "already present" in capsys.readouterr().out
    call_command("seed_demo", "--reset", "--seed", "3")


def test_healthz(client, db):
    response = client.get(reverse("healthz"))
    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "ok" and data["database"] == "ok"
    assert data["version"] == __version__
    assert data["worker"]["healthy"] is False
    services.heartbeat()
    assert client.get(reverse("healthz")).json()["worker"]["healthy"] is True


def test_healthz_reports_database_errors(client, db, monkeypatch):
    from docketbell import health

    class Broken:
        def cursor(self):
            raise RuntimeError("down")

    monkeypatch.setattr(health, "connection", Broken())
    response = client.get(reverse("healthz"))
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"


def test_version_endpoint(client, db):
    assert client.get(reverse("version")).json()["version"] == __version__


def test_build_info_from_environment(monkeypatch):
    monkeypatch.setenv("DOCKETBELL_BUILD_NUMBER", "42")
    monkeypatch.setenv("DOCKETBELL_GIT_SHA", "1a2b3c4d5e6f")
    monkeypatch.setenv("DOCKETBELL_BUILD_DATE", "2026-11-07T12:00:00Z")
    build_info.cache_clear()
    try:
        info = build_info()
        assert info.label == f"Docketbell {__version__} (build 42, 1a2b3c4)"
        assert info.as_dict()["built_at"] == "2026-11-07T12:00:00Z"
    finally:
        build_info.cache_clear()


def test_dev_build_label():
    assert BuildInfo("1.0.0", "dev", "", "").label == "Docketbell 1.0.0 (development build)"


def test_cli_version(capsys):
    main(["docketbell", "--version"])
    assert capsys.readouterr().out.startswith(f"Docketbell {__version__}")


def test_version_is_semver():
    import re

    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", __version__)


def ids(settings_override, settings):
    for key, value in settings_override.items():
        setattr(settings, key, value)
    services._window.cache_clear()
    return {problem.id for problem in checks.check_configuration()}


def test_checks_pass_with_test_settings(settings):
    assert ids({}, settings) == set()


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"DOCKETBELL_SEND_WINDOW": "nonsense"}, "docketbell.E001"),
        ({"DOCKETBELL_SEND_WINDOW": "20:00-08:00"}, "docketbell.E002"),
        ({"DOCKETBELL_SEND_TIME": "21:00"}, "docketbell.E003"),
        ({"DOCKETBELL_REMINDER_DAYS": []}, "docketbell.E004"),
        ({"TIME_ZONE": "Mars/Base"}, "docketbell.E005"),
        ({"DOCKETBELL_ORG_PHONE": ""}, "docketbell.W001"),
        (
            {"SMS_BACKEND": "docketbell.sms.backends.console.ConsoleBackend", "DEBUG": False},
            "docketbell.W003",
        ),
    ],
)
def test_checks_catch_mistakes(settings, override, expected):
    try:
        assert expected in ids(override, settings)
    finally:
        services._window.cache_clear()


def test_check_for_uncompiled_translations(settings, tmp_path):
    settings.LOCALE_PATHS = [tmp_path]
    assert "docketbell.W002" in ids({}, settings)


def test_timezone_now_is_aware():
    assert timezone.is_aware(timezone.now())
