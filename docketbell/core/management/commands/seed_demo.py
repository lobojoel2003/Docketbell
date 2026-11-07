"""Fill the database with a realistic, fictional caseload for demos and screenshots.

Rather than inserting rows directly, this runs the real scheduler, dispatcher
and reply handler while moving a simulated clock forward, so every text,
reply and status you see was produced by the same code that runs in production.
All names are invented and all phone numbers are in the fictional 555-01XX range.
"""

from __future__ import annotations

import datetime as dt
import heapq
import itertools
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from docketbell.core import replies, services
from docketbell.core.models import Court, CourtDate, Message, MessageTemplate, Person, Reminder
from docketbell.sms.backends.base import BaseBackend, SendResult
from docketbell.sms.backends.twilio import UNDELIVERABLE_CODES

PEOPLE = [
    ("Jasmine", "Carter", "en"),
    ("Marcus", "Johnson", "en"),
    ("Ashley", "Brooks", "en"),
    ("Tyrone", "Williams", "en"),
    ("Brianna", "Davis", "en"),
    ("Kevin", "O'Brien", "en"),
    ("Destiny", "Howard", "en"),
    ("Andre", "Thompson", "en"),
    ("Megan", "Kowalski", "en"),
    ("Darnell", "Price", "en"),
    ("Samantha", "Reyes", "en"),
    ("Jordan", "Mitchell", "en"),
    ("Crystal", "Hayes", "en"),
    ("Luis", "Ortega", "en"),
    ("Tasha", "Green", "en"),
    ("Ryan", "Sullivan", "en"),
    ("Keisha", "Moore", "en"),
    ("Derek", "Hall", "en"),
    ("María", "González", "es"),
    ("José", "Hernández", "es"),
    ("Guadalupe", "Ramírez", "es"),
    ("Carlos", "Mendoza", "es"),
    ("Yesenia", "Flores", "es"),
    ("Miguel", "Torres", "es"),
    ("Rosa", "Castillo", "es"),
    ("Juan Carlos", "Vargas", "es"),
    ("Wei", "Chen", "zh-hans"),
    ("Xiu Ying", "Li", "zh-hans"),
    ("Jun", "Zhang", "zh-hans"),
    ("Linh", "Tran", "vi"),
    ("Minh", "Pham", "vi"),
    ("Thu", "Nguyen", "vi"),
    ("Min-jun", "Kim", "ko"),
    ("Ji-woo", "Park", "ko"),
    ("Olga", "Ivanova", "ru"),
    ("Dmitri", "Sokolov", "ru"),
    ("Amina", "Haddad", "ar"),
    ("Omar", "Khalil", "ar"),
    ("Jean", "Baptiste", "ht"),
    ("Marie-Claire", "Joseph", "ht"),
    ("Wilner", "Pierre", "ht"),
]

CONFIRM = {
    "en": ["1", "Yes", "1", "Yes I'll be there", "ok", "1 thank you"],
    "es": ["1", "Sí", "Si, ahí estaré", "1"],
    "zh-hans": ["1", "好的", "是的"],
    "vi": ["1", "Có", "Vâng"],
    "ko": ["1", "네"],
    "ru": ["1", "Да"],
    "ar": ["1", "نعم"],
    "ht": ["1", "Wi"],
}
NEEDS_HELP = {
    "en": ["2", "No I have to work that day", "2 can someone call me"],
    "es": ["2", "No puedo ir, tengo que trabajar"],
    "zh-hans": ["2", "不能去"],
    "ru": ["2", "Нет, не смогу"],
}
QUESTIONS = {
    "en": [
        "What do I need to bring?",
        "I don't have a ride. Is there a bus?",
        "Can I bring my son with me?",
        "Is this the traffic ticket?",
    ],
    "es": ["¿Tengo que llevar algo?", "¿Puedo llevar a mi hija?"],
    "vi": ["Tôi cần mang theo gì?"],
}
HEARINGS = [
    "Arraignment",
    "Pretrial conference",
    "Status hearing",
    "Traffic",
    "Sentencing",
    "Motion hearing",
]
ROOMS = ["Courtroom 2A", "Courtroom 3", "Courtroom 4B", "Courtroom 5", "Part AP-2"]


class DemoBackend(BaseBackend):
    name = "demo"
    _ids = itertools.count(1)

    def send(self, to, body, *, callback_url=None):
        return SendResult(provider_id=f"demo-{next(self._ids):06d}", status="sent")


class Command(BaseCommand):
    help = "Create a fictional caseload (courts, people, court dates, texts and replies)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true", help="Delete all existing court data first."
        )
        parser.add_argument("--seed", type=int, default=7, help="Random seed (default: 7).")
        parser.add_argument("--user", default="", help="Also create this staff user.")
        parser.add_argument("--password", default="", help="Password for --user.")

    def handle(self, *args, reset: bool, seed: int, user: str, password: str, **options):
        if Court.objects.exists() and not reset:
            self.stdout.write("Demo data already present. Use --reset to start over.")
            return
        if reset:
            with transaction.atomic():
                for model in (Reminder, Message, CourtDate, Person, Court, MessageTemplate):
                    model.objects.all().delete()
        if user:
            self._user(user, password)
        rng = random.Random(seed)
        with transaction.atomic():
            counts = self._seed(rng)
        self.stdout.write(
            self.style.SUCCESS(
                f"Created {counts['people']} people, {counts['dates']} court dates and "
                f"{counts['messages']} texts."
            )
        )

    def _user(self, username: str, password: str) -> None:
        User = get_user_model()
        account, created = User.objects.get_or_create(
            username=username,
            defaults={
                "is_staff": True,
                "is_superuser": True,
                "first_name": "Demo",
                "last_name": "Staff",
            },
        )
        if password:
            account.set_password(password)
            account.save()
        self.stdout.write(f"{'Created' if created else 'Updated'} staff user {username!r}.")

    def _seed(self, rng: random.Random) -> dict:
        now = timezone.now()
        tz = timezone.get_default_timezone()
        main = Court.objects.create(
            name="Main Street Courthouse",
            address="100 Main St",
            timezone=str(tz),
            phone="(212) 555-0100",
        )
        east = Court.objects.create(
            name="Eastside Municipal Court",
            address="2200 E 14th St",
            timezone=str(tz),
            phone="(212) 555-0110",
        )
        people = [
            Person.objects.create(
                first_name=first, last_name=last, language=lang, phone=f"+1212555{130 + i:04d}"
            )
            for i, (first, last, lang) in enumerate(PEOPLE)
        ]
        Person.objects.filter(pk=people[9].pk).update(phone="+12125550198")  # landline

        today = timezone.localtime(now, tz).date()

        def at(day: dt.date, hour: int, minute: int) -> dt.datetime:
            return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=tz)

        slots = [(9, 0), (9, 0), (9, 30), (10, 0), (10, 30), (11, 0), (13, 30), (14, 0)]
        plans: list[tuple[Person, dt.datetime]] = []
        # Upcoming: busy weekdays over the next two weeks, including later today.
        upcoming = rng.sample(people, 34)
        for i, person in enumerate(upcoming):
            offset = [0, 0, 1, 1, 1, 1, 2, 2, 3, 3, 4, 4, 4, 6, 7, 7, 8, 9, 9, 10, 10, 11, 13, 13][
                i % 24
            ]
            day = today + dt.timedelta(days=offset)
            while day.weekday() >= 5:
                day += dt.timedelta(days=1)
            hour, minute = rng.choice(slots)
            if offset == 0:
                hour, minute = rng.choice([(14, 0), (15, 30), (16, 0)])
            plans.append((person, at(day, hour, minute)))
        # Past: three months of outcomes.
        for _ in range(78):
            day = today - dt.timedelta(days=rng.randint(2, 88))
            while day.weekday() >= 5:
                day -= dt.timedelta(days=1)
            plans.append((rng.choice(people), at(day, *rng.choice(slots))))

        backend = DemoBackend()
        events: list = []
        seq = itertools.count()

        dispatch_times: set[dt.datetime] = set()

        def push(when, kind, payload):
            if kind == "dispatch":
                if when in dispatch_times:
                    return
                dispatch_times.add(when)
            heapq.heappush(events, (when, next(seq), kind, payload))

        def push_pending(after):
            for send_at in (
                Reminder.objects.filter(status=Reminder.Status.PENDING, send_at__gt=after)
                .values_list("send_at", flat=True)
                .distinct()
            ):
                push(send_at, "dispatch", None)

        for person, starts_at in plans:
            lead = dt.timedelta(days=rng.randint(9, 21), hours=rng.randint(0, 6))
            created = starts_at - lead
            if created > now:  # pragma: no cover - leads are always in the past here
                created = now - dt.timedelta(hours=1)
            created = created.replace(hour=rng.randint(9, 16), minute=rng.randint(0, 59))
            push(created, "create", (person, starts_at))

        behavior: dict[int, str] = {}
        while events:
            when, _, kind, payload = heapq.heappop(events)
            if when > now:
                break
            if kind == "create":
                person, starts_at = payload
                court = main if rng.random() < 0.65 else east
                cd = CourtDate.objects.create(
                    person=person,
                    court=court,
                    starts_at=starts_at,
                    room=rng.choice(ROOMS),
                    hearing_type=rng.choice(HEARINGS),
                    case_number=f"CR-{starts_at.year}-{rng.randint(1000, 9999)}",
                )
                CourtDate.objects.filter(pk=cd.pk).update(created_at=when)
                services.enroll(cd, now=when)
                behavior[cd.pk] = self._behavior(rng, person)
                for send_at in cd.reminders.values_list("send_at", flat=True):
                    push(send_at, "dispatch", None)
                push(starts_at + dt.timedelta(hours=5), "outcome", cd.pk)
            elif kind == "dispatch":
                before = set(Message.objects.filter(direction="out").values_list("pk", flat=True))
                services.dispatch_due(now=when, backend=backend)
                sent = (
                    Message.objects.filter(direction="out")
                    .exclude(pk__in=before)
                    .select_related("court_date", "person")
                )
                for message in sent:
                    self._react(rng, message, behavior, push, when)
                push_pending(when)  # deferred or retried reminders
            elif kind == "reply":
                phone, body = payload
                replies.handle_inbound(
                    phone=phone, body=body, provider_id="", backend=backend, now=when
                )
            elif kind == "outcome":
                cd = CourtDate.objects.select_related("person").get(pk=payload)
                if cd.status != CourtDate.Status.SCHEDULED:
                    continue
                if cd.needs_help:
                    services.resolve_help(cd, now=when)
                chance = 0.94 if cd.confirmed_at else 0.8 if cd.needs_help_at else 0.71
                status = (
                    CourtDate.Status.ATTENDED if rng.random() < chance else CourtDate.Status.MISSED
                )
                services.record_outcome(cd, status, now=when)
                if status == CourtDate.Status.MISSED:
                    push_pending(when - dt.timedelta(seconds=1))

        # Delivery reports: almost everything arrives; the landline never does.
        outbound = Message.objects.filter(direction="out", status="sent")
        for message in outbound.filter(phone="+12125550198"):
            services.record_delivery(
                message.provider_id,
                "undelivered",
                error_code="30006",
                undeliverable_codes=UNDELIVERABLE_CODES,
            )
        outbound.exclude(phone="+12125550198").exclude(
            created_at__gte=now - dt.timedelta(minutes=2)
        ).update(status=Message.Status.DELIVERED)
        # A couple of older replies were already handled by staff.
        for message in Message.objects.filter(
            needs_attention=True, created_at__lt=now - dt.timedelta(days=3)
        ):
            message.handled_at = message.created_at + dt.timedelta(hours=2)
            message.save(update_fields=["handled_at"])
        services.heartbeat("worker", now=now)
        return {
            "people": Person.objects.count(),
            "dates": CourtDate.objects.count(),
            "messages": Message.objects.count(),
        }

    @staticmethod
    def _behavior(rng: random.Random, person: Person) -> str:
        roll = rng.random()
        if roll < 0.56:
            return "confirm"
        if roll < 0.66:
            return "help"
        if roll < 0.72:
            return "question"
        if roll < 0.75:
            return "stop"
        if roll < 0.77 and person.language == "en":
            return "language"
        return "silent"

    @staticmethod
    def _react(rng, message: Message, behavior: dict, push, when) -> None:
        cd = message.court_date
        if cd is None or message.kind not in {"enrollment", "heads_up", "plan"}:
            return
        plan = behavior.get(cd.pk, "silent")
        person = message.person
        lang = person.language
        delay = dt.timedelta(minutes=rng.randint(2, 180))
        if plan == "confirm" and not cd.confirmed_at and message.kind in {"enrollment", "heads_up"}:
            if message.kind == "enrollment" and rng.random() < 0.45:
                return  # some people confirm on the heads-up instead
            push(when + delay, "reply", (person.phone, rng.choice(CONFIRM.get(lang, ["1"]))))
            behavior[cd.pk] = "done"
        elif plan == "help" and message.kind in {"heads_up", "plan"}:
            push(when + delay, "reply", (person.phone, rng.choice(NEEDS_HELP.get(lang, ["2"]))))
            behavior[cd.pk] = "done"
        elif plan == "question" and message.kind == "enrollment":
            push(when + delay, "reply", (person.phone, rng.choice(QUESTIONS.get(lang, ["?"]))))
            behavior[cd.pk] = "confirm"
        elif plan == "stop" and message.kind == "heads_up":
            push(when + delay, "reply", (person.phone, "STOP"))
            behavior[cd.pk] = "done"
        elif plan == "language" and message.kind == "enrollment":
            push(when + delay, "reply", (person.phone, "Español"))
            behavior[cd.pk] = "confirm"
