import sys

from django.core.management.base import BaseCommand, CommandError

from docketbell.core.importer import import_court_dates


class Command(BaseCommand):
    help = "Import court dates from a CSV file (use - to read standard input)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="CSV file, or - for standard input")
        parser.add_argument("--dry-run", action="store_true", help="Check the file; save nothing.")
        parser.add_argument(
            "--no-notify", action="store_true", help="Don't text people whose date changed."
        )

    def handle(self, *args, path: str, dry_run: bool, no_notify: bool, **options):
        try:
            if path == "-":
                report = import_court_dates(sys.stdin, dry_run=dry_run, notify=not no_notify)
            else:
                with open(path, encoding="utf-8-sig", newline="") as handle:
                    report = import_court_dates(handle, dry_run=dry_run, notify=not no_notify)
        except OSError as exc:
            raise CommandError(str(exc)) from exc

        verb = "Would import" if dry_run else "Imported"
        self.stdout.write(
            f"{verb}: {report.created} new, {report.updated} updated, "
            f"{report.unchanged} unchanged, {len(report.skipped)} skipped, "
            f"{len(report.errors)} with problems."
        )
        for line, note in report.skipped:
            self.stdout.write(f"  line {line}: skipped: {note}")
        for line, error in report.errors:
            self.stderr.write(f"  line {line}: {error}")
        if report.errors:
            raise CommandError("Some rows could not be imported.")
