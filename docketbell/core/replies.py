"""Understanding replies.

People answer with a number (1 = confirm, 2 = need help), a word in their own
language ("sí", "có", "да", "네"), a carrier keyword (STOP, START, HELP) or the
name of a language to switch to ("Español", "中文"). Anything else goes to the
staff inbox, and the person gets one gentle "we couldn't read that" per day.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import unicodedata

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from docketbell.core import copy, services
from docketbell.core.models import CourtDate, Message, Person
from docketbell.core.phone import mask, normalize
from docketbell.sms import BaseBackend

log = logging.getLogger("docketbell")

Intent = Message.Intent


def normalize_text(text: str) -> str:
    """Casefold, drop accents and punctuation, collapse spaces. Keeps CJK and Hangul intact."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = unicodedata.normalize("NFC", text).casefold()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _words(*items: str) -> frozenset[str]:
    return frozenset(normalize_text(item) for item in items)


# Carrier keywords must match the whole message, as carriers do.
STOP_WORDS = _words(
    "stop",
    "stopall",
    "stop all",
    "unsubscribe",
    "cancel",
    "end",
    "quit",
    "revoke",
    "optout",
    "opt out",
    "alto",
    "parar",
    "detener",
    "baja",
    "停止",
    "退订",
    "dừng",
    "ngừng",
    "중지",
    "стоп",
    "отписаться",
    "توقف",
    "kanpe",
    "sispann",
)
START_WORDS = _words("start", "unstop", "subscribe", "resume", "iniciar", "comenzar")
INFO_WORDS = _words(
    "help", "info", "ayuda", "información", "帮助", "giúp", "도움말", "помощь", "مساعدة", "èd"
)

# First word of the message.
CONFIRM_WORDS = _words(
    "1",
    "yes",
    "y",
    "yeah",
    "yep",
    "ok",
    "okay",
    "confirm",
    "confirmed",
    "sure",
    "sí",
    "si",
    "confirmo",
    "confirmado",
    "claro",
    "是",
    "是的",
    "好",
    "好的",
    "确认",
    "對",
    "对",
    "có",
    "vâng",
    "dạ",
    "xác nhận",
    "ừ",
    "네",
    "예",
    "확인",
    "응",
    "да",
    "подтверждаю",
    "ок",
    "نعم",
    "أكيد",
    "تأكيد",
    "wi",
    "konfime",
)
NEEDS_HELP_WORDS = _words(
    "2",
    "no",
    "nope",
    "cant",
    "can't",
    "cannot",
    "no puedo",
    "necesito",
    "不",
    "不能",
    "不行",
    "không",
    "아니요",
    "아니",
    "못",
    "нет",
    "не",
    "لا",
    "non",
    "pa",
)

_CJK_CONFIRM_PREFIXES = ("是的", "好的", "确认", "確認")
_CJK_NEEDS_HELP_PREFIXES = ("不能", "不行", "去不了", "来不了", "來不了")

LANGUAGE_NAMES: dict[str, str] = {}
_LANGUAGE_ALIASES = {
    "en": ["english", "inglés", "ingles", "eng"],
    "es": ["español", "espanol", "spanish", "castellano"],
    "zh-hans": ["中文", "汉语", "普通话", "简体中文", "chinese", "mandarin", "zhongwen"],
    "vi": ["tiếng việt", "tieng viet", "vietnamese", "việt", "viet"],
    "ko": ["한국어", "한국말", "korean", "hangugeo"],
    "ru": ["русский", "по-русски", "russian", "russkiy"],
    "ar": ["العربية", "عربي", "arabic", "arabi"],
    "ht": ["kreyòl", "kreyol", "kreyòl ayisyen", "creole", "haitian", "haitian creole"],
}


def language_names() -> dict[str, str]:
    if not LANGUAGE_NAMES:
        enabled = dict(settings.DOCKETBELL_LANGUAGES)
        for code, aliases in _LANGUAGE_ALIASES.items():
            if code not in enabled:
                continue
            for alias in [*aliases, enabled[code]]:
                LANGUAGE_NAMES[normalize_text(alias)] = code
    return LANGUAGE_NAMES


def classify(body: str) -> tuple[str, str | None]:
    """Return ``(intent, language_code)`` for an incoming text."""
    text = normalize_text(body)
    if not text:
        return Intent.UNKNOWN, None
    if text in STOP_WORDS or text.split()[0] in {"stop", "alto"}:
        return Intent.STOP, None
    if text in START_WORDS:
        return Intent.START, None
    if text in INFO_WORDS:
        return Intent.INFO, None
    language = language_names().get(text)
    if language:
        return Intent.LANGUAGE, language
    words = text.split()
    for candidate in (text, " ".join(words[:2]), words[0]):
        if candidate in CONFIRM_WORDS:
            return Intent.CONFIRM, None
        if candidate in NEEDS_HELP_WORDS:
            return Intent.NEEDS_HELP, None
    # Chinese replies have no spaces: "好的谢谢", "是的我会去", "不能去".
    if len(text) <= 12:
        if text.startswith(_CJK_CONFIRM_PREFIXES):
            return Intent.CONFIRM, None
        if text.startswith(_CJK_NEEDS_HELP_PREFIXES):
            return Intent.NEEDS_HELP, None
    return Intent.UNKNOWN, None


def _match(phone: str, now: dt.datetime) -> tuple[Person | None, CourtDate | None]:
    """Find who texted and which court date they most likely mean."""
    people = list(Person.objects.filter(phone=phone))
    if not people:
        return None, None
    court_date = (
        CourtDate.objects.with_people()
        .filter(
            person__in=people,
            status=CourtDate.Status.SCHEDULED,
            starts_at__gte=now - dt.timedelta(hours=12),
        )
        .order_by("starts_at")
        .first()
    )
    if court_date is not None:
        return court_date.person, court_date
    return max(people, key=lambda p: p.updated_at), None


def _recently_sent(phone: str, kind: str, now: dt.datetime, hours: int = 24) -> bool:
    return Message.objects.filter(
        phone=phone,
        direction=Message.Direction.OUTBOUND,
        kind=kind,
        created_at__gte=now - dt.timedelta(hours=hours),
    ).exists()


@transaction.atomic
def handle_inbound(
    *,
    phone: str,
    body: str,
    provider_id: str = "",
    backend: BaseBackend | None = None,
    now: dt.datetime | None = None,
) -> Message:
    """Record an incoming text, act on it and send the right answer."""
    now = now or timezone.now()
    phone = normalize(phone) or phone.strip()
    if provider_id:
        existing = Message.objects.filter(
            direction=Message.Direction.INBOUND, provider_id=provider_id
        ).first()
        if existing is not None:
            return existing  # providers retry webhooks; handle each text once

    person, court_date = _match(phone, now)
    intent, language = classify(body)
    message = Message.objects.create(
        person=person,
        court_date=court_date,
        direction=Message.Direction.INBOUND,
        phone=phone,
        body=body.strip()[:1600],
        language=person.language if person else "",
        intent=intent,
        backend=backend.name if backend else "",
        provider_id=provider_id,
        status=Message.Status.RECEIVED,
        created_at=now,
    )
    log.info("SMS from %s understood as %s", mask(phone), intent)

    def reply(kind: str, *, lang: str | None = None, target: Person | None = None) -> None:
        target = target or person
        if target is None:
            return
        services.send_to_person(
            target, kind, court_date=court_date, language=lang, backend=backend, now=now
        )

    if intent == Intent.STOP:
        Person.objects.filter(phone=phone, opted_out_at__isnull=True).update(opted_out_at=now)
        if person is not None:
            person.refresh_from_db()
            if settings.DOCKETBELL_SEND_OPT_OUT_CONFIRMATION:
                reply(copy.Kind.REPLY_STOP)
        return message

    if intent == Intent.START:
        Person.objects.filter(phone=phone).update(opted_out_at=None)
        if person is not None:
            person.refresh_from_db()
            reply(copy.Kind.REPLY_START)
        return message

    if person is None:
        # Unknown number: never auto-reply, but make sure staff see it.
        message.needs_attention = True
        message.save(update_fields=["needs_attention"])
        return message

    if person.is_opted_out:
        # Respect the opt-out: record what they said, flag it for staff, don't answer.
        if intent in (Intent.UNKNOWN, Intent.NEEDS_HELP):
            message.needs_attention = True
            message.save(update_fields=["needs_attention"])
        if court_date is not None and intent == Intent.NEEDS_HELP:
            services.mark_needs_help(court_date, now=now)
        if court_date is not None and intent == Intent.CONFIRM:
            services.mark_confirmed(court_date, now=now)
        return message

    if intent == Intent.CONFIRM:
        if court_date is None:
            reply(copy.Kind.REPLY_NO_COURT_DATE)
        else:
            services.mark_confirmed(court_date, now=now)
            reply(copy.Kind.REPLY_CONFIRMED)
    elif intent == Intent.NEEDS_HELP:
        message.needs_attention = True
        message.save(update_fields=["needs_attention"])
        if court_date is not None:
            services.mark_needs_help(court_date, now=now)
        reply(copy.Kind.REPLY_HELP)
    elif intent == Intent.INFO:
        reply(copy.Kind.REPLY_INFO)
    elif intent == Intent.LANGUAGE and language:
        Person.objects.filter(phone=phone).update(language=language)
        person.refresh_from_db()
        reply(copy.Kind.REPLY_LANGUAGE, lang=language)
    else:
        message.needs_attention = True
        message.save(update_fields=["needs_attention"])
        if not _recently_sent(phone, copy.Kind.REPLY_UNKNOWN, now):
            reply(copy.Kind.REPLY_UNKNOWN)
    return message
