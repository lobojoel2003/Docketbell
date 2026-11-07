from __future__ import annotations

import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from docketbell.core import importer
from docketbell.core.models import CourtDate, Person, Reminder
from tests.conftest import NOW, local

HEADER = (
    "first_name,last_name,phone,language,court,date,time,room,hearing_type,case_number,"
    "external_id\n"
)


def run(rows: str, **kwargs):
    kwargs.setdefault("now", NOW)
    return importer.import_court_dates(io.StringIO(HEADER + rows), **kwargs)


def test_import_creates_people_and_court_dates(court):
    report = run(
        "Maria,Lopez,(212) 555-0142,Spanish,Main Street Courthouse,2026-11-17,9:30 AM,4B,"
        "Arraignment,CR-1,c-1\n"
        "Wei,Chen,212-555-0143,zh,main street courthouse,11/18/2026,14:00,,,,c-2\n"
    )
    assert (report.created, report.updated, report.unchanged, report.errors) == (2, 0, 0, [])
    maria = CourtDate.objects.get(external_id="c-1")
    assert maria.person.language == "es"
    assert maria.person.phone == "+12125550142"
    assert maria.starts_at == local(2026, 11, 17, 9, 30)
    assert maria.reminders.filter(kind=Reminder.Kind.ENROLLMENT).exists()
    assert CourtDate.objects.get(external_id="c-2").person.language == "zh-hans"


def test_reimport_is_idempotent_and_reschedules_moved_dates(court):
    row = "Maria,Lopez,2125550142,es,Main Street Courthouse,2026-11-17,09:30,,,,c-1\n"
    run(row)
    assert run(row).unchanged == 1
    moved = run(row.replace("09:30", "13:00"))
    assert moved.updated == 1
    court_date = CourtDate.objects.get(external_id="c-1")
    assert court_date.starts_at == local(2026, 11, 17, 13)
    assert Person.objects.count() == 1


def test_matching_without_external_id(court):
    row = "Maria,,2125550142,,Main Street Courthouse,2026-11-17,09:30,4B,,,\n"
    run(row)
    assert run(row.replace(",4B,", ",5C,")).updated == 1
    assert CourtDate.objects.get().room == "5C"


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (",Lopez,2125550142,,Main Street Courthouse,2026-11-17,09:30,,,,", "first_name"),
        ("Maria,,12345,,Main Street Courthouse,2026-11-17,09:30,,,,", "valid phone"),
        ("Maria,,2125550142,,Nowhere Court,2026-11-17,09:30,,,,", "Unknown court"),
        ("Maria,,2125550142,,Main Street Courthouse,17th Nov,09:30,,,,", "date"),
        ("Maria,,2125550142,,Main Street Courthouse,2026-11-17,lunch,,,,", "time"),
        ("Maria,,2125550142,Klingon,Main Street Courthouse,2026-11-17,09:30,,,,", "language"),
    ],
)
def test_bad_rows_are_reported_and_good_rows_still_import(court, row, message):
    good = "Wei,,2125550143,,Main Street Courthouse,2026-11-18,10:00,,,,\n"
    report = run(row + "\n" + good)
    assert report.created == 1
    assert len(report.errors) == 1
    line, error = report.errors[0]
    assert line == 2 and message in error


def test_past_dates_are_skipped(court):
    report = run("Maria,,2125550142,,Main Street Courthouse,2026-10-01,09:30,,,,\n")
    assert report.created == 0 and report.skipped[0][1] == "Court date is in the past."


def test_dry_run_saves_nothing(court):
    report = run("Maria,,2125550142,,Main Street Courthouse,2026-11-17,09:30,,,,\n", dry_run=True)
    assert report.created == 1 and report.dry_run
    assert not CourtDate.objects.exists() and not Person.objects.exists()


def test_missing_columns(court):
    report = importer.import_court_dates(io.StringIO("name,phone\nMaria,1\n"))
    assert report.errors == [(1, "Missing columns: first_name, court, date, time")]


def test_bytes_with_bom_and_messy_headers(court):
    data = (
        "﻿First Name,Phone,Court,Date,Time\n"
        "Maria,2125550142,Main Street Courthouse,2026-11-17,9:30 a.m.\n"
    ).encode()
    report = importer.import_court_dates(data, now=NOW)
    assert report.created == 1
    assert report.rows == 1


def test_command(tmp_path, court, capsys):
    path = tmp_path / "dates.csv"
    path.write_text(HEADER + "Maria,,2125550142,,Main Street Courthouse,2027-01-05,09:30,,,,\n")
    call_command("import_court_dates", str(path), "--dry-run")
    assert "Would import: 1 new" in capsys.readouterr().out
    call_command("import_court_dates", str(path))
    assert CourtDate.objects.count() == 1
    path.write_text(HEADER + "Maria,,bad,,Main Street Courthouse,2027-01-05,09:30,,,,\n")
    with pytest.raises(CommandError):
        call_command("import_court_dates", str(path))
    with pytest.raises(CommandError):
        call_command("import_court_dates", str(tmp_path / "missing.csv"))
