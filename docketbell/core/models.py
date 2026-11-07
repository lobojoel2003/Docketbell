"""Data model.

A *Person* has one or more *CourtDates* at a *Court*. Each court date gets a
handful of scheduled *Reminders*; when a reminder goes out it produces an
outbound *Message*. Replies come back as inbound Messages and update the court
date (confirmed, needs help) or the person (opted out, language).
"""

from __future__ import annotations

import zoneinfo
from functools import cached_property

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from docketbell.core import phone as phone_utils


def default_timezone() -> str:
    return settings.TIME_ZONE


def validate_timezone(value: str) -> None:
    try:
        zoneinfo.ZoneInfo(value)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError(
            _("%(value)s is not a known time zone."), params={"value": value}
        ) from exc


def language_choices() -> list[tuple[str, str]]:
    return list(settings.DOCKETBELL_LANGUAGES)


class Court(models.Model):
    name = models.CharField(_("name"), max_length=200, unique=True)
    address = models.CharField(
        _("address"),
        max_length=300,
        blank=True,
        help_text=_("One line, written the way it should appear in texts."),
    )
    timezone = models.CharField(
        _("time zone"), max_length=64, default=default_timezone, validators=[validate_timezone]
    )
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    website = models.URLField(_("website"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("court")
        verbose_name_plural = _("courts")

    def __str__(self) -> str:
        return self.name

    @property
    def tzinfo(self) -> zoneinfo.ZoneInfo:
        return zoneinfo.ZoneInfo(self.timezone)


class Person(models.Model):
    class PhoneStatus(models.TextChoices):
        OK = "ok", _("OK")
        UNDELIVERABLE = "undeliverable", _("Undeliverable")

    first_name = models.CharField(_("first name"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=100, blank=True)
    phone = models.CharField(
        _("mobile phone"),
        max_length=20,
        db_index=True,
        help_text=_("Stored in international format, e.g. +12125550123."),
    )
    language = models.CharField(
        _("language"), max_length=10, choices=language_choices, default="en"
    )
    opted_out_at = models.DateTimeField(_("opted out"), null=True, blank=True)
    phone_status = models.CharField(
        _("phone status"), max_length=20, choices=PhoneStatus.choices, default=PhoneStatus.OK
    )
    external_id = models.CharField(
        _("external ID"),
        max_length=100,
        blank=True,
        db_index=True,
        help_text=_("ID from your case management system, if any."),
    )
    notes = models.TextField(_("notes"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = _("person")
        verbose_name_plural = _("people")

    def __str__(self) -> str:
        return self.full_name

    def clean(self) -> None:
        super().clean()
        if self.phone:
            self.phone = phone_utils.normalize_or_raise(self.phone)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or str(_("Name removed"))

    @property
    def initials(self) -> str:
        parts = [self.first_name[:1], self.last_name[:1]]
        return "".join(p for p in parts if p).upper() or "?"

    @property
    def phone_display(self) -> str:
        return phone_utils.display(self.phone)

    @property
    def is_opted_out(self) -> bool:
        return self.opted_out_at is not None

    @property
    def is_reachable(self) -> bool:
        return not self.is_opted_out and self.phone_status == self.PhoneStatus.OK


class Response(models.TextChoices):
    """Where a court date stands from the person's side, shown on the dashboard."""

    NEEDS_HELP = "needs_help", _("Needs help")
    CONFIRMED = "confirmed", _("Confirmed")
    NO_REPLY = "no_reply", _("No reply yet")
    UNREACHABLE = "unreachable", _("Can't reach")


class CourtDateQuerySet(models.QuerySet):
    def upcoming(self, now=None):
        now = now or timezone.now()
        return self.filter(status=CourtDate.Status.SCHEDULED, starts_at__gte=now)

    def with_people(self):
        return self.select_related("person", "court")


class CourtDate(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", _("Scheduled")
        CANCELED = "canceled", _("Canceled")
        ATTENDED = "attended", _("Attended")
        MISSED = "missed", _("Missed")

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="court_dates", verbose_name=_("person")
    )
    court = models.ForeignKey(
        Court, on_delete=models.PROTECT, related_name="court_dates", verbose_name=_("court")
    )
    starts_at = models.DateTimeField(_("date and time"), db_index=True)
    room = models.CharField(
        _("room"), max_length=100, blank=True, help_text=_("For example: Courtroom 4B")
    )
    hearing_type = models.CharField(
        _("hearing type"), max_length=100, blank=True, help_text=_("For example: Arraignment")
    )
    case_number = models.CharField(
        _("case number"),
        max_length=100,
        blank=True,
        help_text=_("For staff only. Never included in texts."),
    )
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.SCHEDULED, db_index=True
    )
    confirmed_at = models.DateTimeField(_("confirmed"), null=True, blank=True)
    needs_help_at = models.DateTimeField(_("asked for help"), null=True, blank=True)
    help_resolved_at = models.DateTimeField(_("help resolved"), null=True, blank=True)
    external_id = models.CharField(_("external ID"), max_length=100, blank=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CourtDateQuerySet.as_manager()

    class Meta:
        ordering = ["starts_at"]
        verbose_name = _("court date")
        verbose_name_plural = _("court dates")
        indexes = [models.Index(fields=["status", "starts_at"])]

    def __str__(self) -> str:
        local = self.local_starts_at
        return f"{self.person} · {self.court} · {local:%Y-%m-%d %H:%M}"

    @property
    def local_starts_at(self):
        return timezone.localtime(self.starts_at, self.court.tzinfo)

    @property
    def needs_help(self) -> bool:
        return self.needs_help_at is not None and self.help_resolved_at is None

    @property
    def is_upcoming(self) -> bool:
        return self.status == self.Status.SCHEDULED and self.starts_at >= timezone.now()

    @property
    def response(self) -> Response:
        if self.needs_help:
            return Response.NEEDS_HELP
        if self.confirmed_at:
            return Response.CONFIRMED
        if not self.person.is_reachable:
            return Response.UNREACHABLE
        return Response.NO_REPLY

    @cached_property
    def place(self) -> str:
        """Court, room and address as one line for texts."""
        parts = [self.court.name, self.room, self.court.address]
        return ", ".join(p.strip() for p in parts if p and p.strip())


class Message(models.Model):
    class Direction(models.TextChoices):
        OUTBOUND = "out", _("Sent")
        INBOUND = "in", _("Received")

    class Status(models.TextChoices):
        SENT = "sent", _("Sent")
        DELIVERED = "delivered", _("Delivered")
        UNDELIVERED = "undelivered", _("Not delivered")
        FAILED = "failed", _("Failed")
        RECEIVED = "received", _("Received")

    class Intent(models.TextChoices):
        CONFIRM = "confirm", _("Confirmed")
        NEEDS_HELP = "needs_help", _("Asked for help")
        STOP = "stop", _("Opted out")
        START = "start", _("Opted back in")
        INFO = "info", _("Asked for info")
        LANGUAGE = "language", _("Changed language")
        UNKNOWN = "unknown", _("Needs a reply")

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, null=True, blank=True, related_name="messages"
    )
    court_date = models.ForeignKey(
        CourtDate, on_delete=models.SET_NULL, null=True, blank=True, related_name="messages"
    )
    direction = models.CharField(max_length=3, choices=Direction.choices)
    phone = models.CharField(max_length=20, db_index=True)
    body = models.TextField()
    language = models.CharField(max_length=10, blank=True)
    kind = models.CharField(max_length=30, blank=True)
    intent = models.CharField(max_length=20, choices=Intent.choices, blank=True)
    backend = models.CharField(max_length=50, blank=True)
    provider_id = models.CharField(max_length=100, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    error = models.CharField(max_length=300, blank=True)
    segments = models.PositiveSmallIntegerField(default=1)
    needs_attention = models.BooleanField(default=False, db_index=True)
    handled_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = _("message")
        verbose_name_plural = _("messages")

    def __str__(self) -> str:
        arrow = "→" if self.direction == self.Direction.OUTBOUND else "←"
        return f"{arrow} {phone_utils.mask(self.phone)}: {self.body[:40]}"

    @property
    def is_outbound(self) -> bool:
        return self.direction == self.Direction.OUTBOUND

    @property
    def kind_label(self) -> str:
        from docketbell.core import copy

        spec = copy.KINDS.get(self.kind)
        if spec is not None:
            return spec.label
        return _("Staff text") if self.kind == "manual" else _("Text")


class Reminder(models.Model):
    class Kind(models.TextChoices):
        ENROLLMENT = "enrollment", _("Welcome")
        HEADS_UP = "heads_up", _("Heads-up")
        PLAN = "plan", _("Make a plan")
        TOMORROW = "tomorrow", _("Day before")
        TODAY = "today", _("Morning of")
        RESCHEDULED = "rescheduled", _("Date changed")
        CANCELED = "canceled", _("Date canceled")
        MISSED = "missed", _("Missed court")

    class Status(models.TextChoices):
        PENDING = "pending", _("Scheduled")
        SENT = "sent", _("Sent")
        FAILED = "failed", _("Failed")
        CANCELED = "canceled", _("Canceled")
        SKIPPED = "skipped", _("Skipped")

    # Reminders that only make sense before the court date starts.
    BEFORE_HEARING = frozenset(
        {Kind.ENROLLMENT, Kind.HEADS_UP, Kind.PLAN, Kind.TOMORROW, Kind.TODAY, Kind.RESCHEDULED}
    )
    # Countdown reminders, replaced whenever the schedule is rebuilt.
    COUNTDOWN = frozenset({Kind.HEADS_UP, Kind.PLAN, Kind.TOMORROW, Kind.TODAY})

    court_date = models.ForeignKey(CourtDate, on_delete=models.CASCADE, related_name="reminders")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    send_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    detail = models.CharField(max_length=300, blank=True)
    message = models.OneToOneField(
        Message, on_delete=models.SET_NULL, null=True, blank=True, related_name="reminder"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["send_at", "id"]
        verbose_name = _("reminder")
        verbose_name_plural = _("reminders")
        indexes = [models.Index(fields=["status", "send_at"])]

    def __str__(self) -> str:
        return (
            f"{self.get_kind_display()} for {self.court_date_id} at {self.send_at:%Y-%m-%d %H:%M}"
        )


class MessageTemplate(models.Model):
    """Optional per-language override of the built-in message copy."""

    kind = models.CharField(_("message"), max_length=30)
    language = models.CharField(_("language"), max_length=10, choices=language_choices)
    body = models.TextField(_("text"))
    is_active = models.BooleanField(_("active"), default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["kind", "language"]
        verbose_name = _("custom message text")
        verbose_name_plural = _("custom message texts")
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "language"], name="unique_template_per_language"
            )
        ]

    def __str__(self) -> str:
        return f"{self.kind} ({self.language})"

    def clean(self) -> None:
        from docketbell.core import copy

        super().clean()
        if self.kind not in copy.KINDS:
            raise ValidationError({"kind": _("Unknown message kind.")})
        unknown = copy.unknown_placeholders(self.body)
        if unknown:
            raise ValidationError(
                {
                    "body": _("Unknown placeholders: %(names)s. Allowed: %(allowed)s.")
                    % {
                        "names": ", ".join(f"{{{n}}}" for n in sorted(unknown)),
                        "allowed": ", ".join(f"{{{n}}}" for n in copy.PLACEHOLDERS),
                    }
                }
            )


class Heartbeat(models.Model):
    """Last time a background worker checked in, so the dashboard can warn if none is running."""

    name = models.CharField(max_length=100, primary_key=True)
    seen_at = models.DateTimeField()
    version = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = _("worker heartbeat")
        verbose_name_plural = _("worker heartbeats")

    def __str__(self) -> str:
        return f"{self.name} @ {self.seen_at:%Y-%m-%d %H:%M:%S}"
