import datetime as dt

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from docketbell.core.models import CourtDate, Message, Person


class Command(BaseCommand):
    help = (
        "Delete court dates, texts and people older than the retention period. "
        "People who opted out keep a minimal record (phone number and opt-out date) so they "
        "are never texted again."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=settings.DOCKETBELL_RETENTION_DAYS,
            help="Keep this many days after each court date (default: DOCKETBELL_RETENTION_DAYS).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Report only; delete nothing.")

    @transaction.atomic
    def handle(self, *args, days: int, dry_run: bool, **options):
        if days <= 0:
            raise CommandError("Set --days or DOCKETBELL_RETENTION_DAYS to a positive number.")
        cutoff = timezone.now() - dt.timedelta(days=days)

        old_dates = CourtDate.objects.filter(starts_at__lt=cutoff)
        old_messages = Message.objects.filter(created_at__lt=cutoff)
        n_dates, n_messages = old_dates.count(), old_messages.count()
        old_dates.delete()
        old_messages.delete()

        idle = Person.objects.annotate(last_date=Max("court_dates__starts_at")).filter(
            last_date__isnull=True, created_at__lt=cutoff
        )
        opted_out = idle.filter(opted_out_at__isnull=False)
        n_scrubbed = opted_out.exclude(first_name="").update(
            first_name="", last_name="", notes="", external_id=""
        )
        removable = idle.filter(opted_out_at__isnull=True)
        n_people = removable.count()
        removable.delete()

        self.stdout.write(
            f"{'Would delete' if dry_run else 'Deleted'} {n_dates} court dates, "
            f"{n_messages} texts and {n_people} records of people; "
            f"kept {n_scrubbed} opt-outs with names removed."
        )
        if dry_run:
            transaction.set_rollback(True)
