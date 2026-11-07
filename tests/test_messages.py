"""The texts are the product: check every one, in every language."""

from __future__ import annotations

import datetime as dt
import re

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import translation

from docketbell.core import copy, formatting
from docketbell.core.models import MessageTemplate
from docketbell.sms.segments import analyze
from tests.conftest import local

LANGUAGES = [code for code, _ in settings.DOCKETBELL_LANGUAGES]
KEYWORDS = re.compile(r"(?<![\w])(1|2|STOP|START)(?![\w])")


def translated(kind: str, language: str) -> str:
    with translation.override(language):
        return str(copy.KINDS[kind].text)


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("kind", list(copy.KINDS))
def test_every_text_is_translated_and_keeps_placeholders(kind, language):
    english = translated(kind, "en")
    text = translated(kind, language)
    if language != "en":
        assert text != english, f"{kind} is not translated into {language}"
    assert copy.placeholders_in(text) == copy.placeholders_in(english)
    assert set(KEYWORDS.findall(text)) >= set(KEYWORDS.findall(english))


@pytest.mark.parametrize("kind", list(copy.KINDS))
def test_english_texts_use_the_cheap_sms_alphabet(kind):
    body = copy.fill(translated(kind, "en"), copy.sample_context("en"))
    info = analyze(body)
    assert info.encoding == "GSM-7", f"{kind} has non-GSM characters: {info.non_gsm}"
    assert info.segments <= 2, f"{kind} is {info.segments} segments long"


@pytest.mark.parametrize("language", LANGUAGES)
def test_language_change_reply_names_its_own_language(language):
    text = translated(copy.Kind.REPLY_LANGUAGE, language)
    if language != "en":
        assert "English" not in text


def test_heads_up_explains_the_consequence():
    text = translated(copy.Kind.HEADS_UP, "en")
    assert "warrant" in text
    assert "{date}" in text and "{time}" in text and "{place}" in text


def test_fill_never_reexpands_values():
    text = copy.fill("Hi {first_name}, see you {date}.", {"first_name": "{date}", "date": "Tue"})
    assert text == "Hi {date}, see you Tue."


def test_fill_tidies_empty_values():
    assert copy.fill("At {place} , {room}.", {"place": "Court", "room": ""}) == "At Court,."


def test_spanish_uses_singular_article_for_one_oclock():
    text = copy.fill("el {date} a las {time}.", {"date": "martes", "time": "1:30 p.m."}, "es")
    assert text == "el martes a la 1:30 p.m."
    text = copy.fill("el {date} a las {time}.", {"date": "martes", "time": "11:30 a.m."}, "es")
    assert text == "el martes a las 11:30 a.m."


def test_render_for_court_date(court_date):
    body = copy.render_for(copy.Kind.HEADS_UP, person=court_date.person, court_date=court_date)
    assert body.startswith("Maria, your court date is Tuesday, November 17 at 9:30 AM, ")
    assert "Main Street Courthouse, Courtroom 4B, 100 Main St" in body
    assert court_date.case_number not in body or not court_date.case_number


def test_render_in_spanish(court_date):
    court_date.person.language = "es"
    body = copy.render_for(copy.Kind.HEADS_UP, person=court_date.person, court_date=court_date)
    assert "martes, 17 de noviembre" in body
    assert "9:30 a.m." in body


def test_org_phone_falls_back_to_court_phone(settings, court_date):
    settings.DOCKETBELL_ORG_PHONE = ""
    assert copy.org_phone(court_date) == "(212) 555-0100"
    assert copy.org_phone(None) == ""


def test_custom_template_overrides_default(db, court_date):
    MessageTemplate.objects.create(
        kind=copy.Kind.TOMORROW, language="en", body="See you tomorrow at {time}, {first_name}!"
    )
    body = copy.render_for(copy.Kind.TOMORROW, person=court_date.person, court_date=court_date)
    assert body == "See you tomorrow at 9:30 AM, Maria!"
    assert copy.template_for(copy.Kind.TOMORROW, "es")[1] is False


def test_custom_template_validation(db):
    template = MessageTemplate(kind=copy.Kind.TOMORROW, language="en", body="Hi {nickname}")
    with pytest.raises(ValidationError) as error:
        template.full_clean()
    assert "nickname" in str(error.value)
    with pytest.raises(ValidationError):
        MessageTemplate(kind="nope", language="en", body="Hi").full_clean()


def test_message_kind_labels(db):
    from docketbell.core.models import Message

    assert Message(kind="heads_up").kind_label == "Heads-up"
    assert Message(kind="manual").kind_label == "Staff text"
    assert Message(kind="").kind_label == "Text"


# --- Dates and times ----------------------------------------------------------

MOMENT = local(2026, 11, 17, 14, 30)


@pytest.mark.parametrize(
    ("language", "date", "time"),
    [
        ("en", "Tuesday, November 17", "2:30 PM"),
        ("es", "martes, 17 de noviembre", "2:30 p.m."),
        ("zh-hans", "11月17日星期二", "下午2:30"),
        ("vi", "Thứ Ba, 17 tháng 11", "14:30"),
        ("ko", "11월 17일 화요일", "오후 2:30"),
        ("ru", "вторник, 17 ноября", "14:30"),
        ("ar", "الثلاثاء، 17 نوفمبر", "2:30 م"),
        ("ht", "madi 17 novanm", "2:30 PM"),
    ],
)
def test_dates_read_naturally(language, date, time):
    assert formatting.format_date(MOMENT, language) == date
    assert formatting.format_time(MOMENT, language) == time


@pytest.mark.parametrize("language", LANGUAGES)
def test_formatted_values_use_plain_spaces(language):
    for value in (
        formatting.format_date(MOMENT, language),
        formatting.format_time(MOMENT, language),
    ):
        assert " " not in value and " " not in value


def test_format_date_accepts_plain_dates():
    assert formatting.format_date(dt.date(2026, 11, 17), "en") == "Tuesday, November 17"


def test_widen_leaves_quoted_literals_alone():
    assert formatting._widen("E, d 'de' MMM 'c'") == "EEEE, d 'de' MMMM 'c'"


def test_unknown_language_falls_back_to_english():
    assert formatting.babel_locale("xx") == "en_US"
