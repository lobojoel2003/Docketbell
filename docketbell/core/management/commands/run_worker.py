import logging
import signal
import threading

from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection

from docketbell.core import services
from docketbell.version import build_info

log = logging.getLogger("docketbell.worker")


class Command(BaseCommand):
    help = "Send reminders as they come due. Runs until stopped (Ctrl+C or SIGTERM)."

    def add_arguments(self, parser):
        from django.conf import settings

        parser.add_argument(
            "--interval",
            type=int,
            default=settings.DOCKETBELL_WORKER_INTERVAL,
            help="Seconds between checks (default: %(default)s).",
        )
        parser.add_argument("--once", action="store_true", help="Check once, then exit.")
        parser.add_argument("--name", default="worker", help="Name shown in worker heartbeats.")

    def handle(self, *args, interval: int, once: bool, name: str, **options):
        stop = threading.Event()

        def request_stop(signum, frame):
            log.info("Stopping after the current batch…")
            stop.set()

        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, request_stop)
            signal.signal(signal.SIGINT, request_stop)

        log.info("%s worker started; checking every %ss", build_info().label, interval)
        while not stop.is_set():
            if not connection.in_atomic_block:
                close_old_connections()  # drop stale connections between batches
            try:
                results = services.dispatch_due()
                services.heartbeat(name)
            except Exception:
                log.exception("Reminder dispatch failed; will try again")
            else:
                if results:
                    log.info(
                        "Reminders: %s", ", ".join(f"{k} {v}" for k, v in sorted(results.items()))
                    )
            if once:
                break
            stop.wait(max(interval, 1))
        log.info("Worker stopped")
