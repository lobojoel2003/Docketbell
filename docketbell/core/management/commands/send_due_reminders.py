from django.core.management.base import BaseCommand

from docketbell.core import services


class Command(BaseCommand):
    help = (
        "Send every reminder that is due, then exit. For running from cron instead of run_worker."
    )

    def handle(self, *args, **options):
        results = services.dispatch_due()
        services.heartbeat("cron")
        summary = ", ".join(f"{k}: {v}" for k, v in sorted(results.items())) or "nothing due"
        self.stdout.write(summary)
