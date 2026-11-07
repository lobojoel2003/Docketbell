"""Run a demo server with fictional data at a fixed point in time.

Used to produce the screenshots in docs/images, so they are reproducible:

    DATABASE_URL=postgres://... python scripts/demo_server.py --port 8001
    node scripts/screenshots.cjs http://127.0.0.1:8001 docs/images

The clock is frozen at a Tuesday morning (it still ticks), so the dashboard
shows a realistic "today" and "tomorrow". Never point this at a real database:
it deletes all court data before seeding.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import zoneinfo
from pathlib import Path

import time_machine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEMO_NOW = dt.datetime(2026, 11, 10, 10, 20, tzinfo=zoneinfo.ZoneInfo("America/New_York"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", default="8001")
    parser.add_argument("--no-seed", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "docketbell.settings")
    os.environ.setdefault("DEBUG", "true")
    os.environ.setdefault("TIME_ZONE", "America/New_York")
    os.environ.setdefault("DOCKETBELL_ORG_NAME", "Main Street Defenders")
    os.environ.setdefault("DOCKETBELL_ORG_PHONE", "(212) 555-0199")
    os.environ.setdefault("DOCKETBELL_ALLOW_SIMULATED_REPLIES", "true")

    with time_machine.travel(DEMO_NOW, tick=True):
        import django
        from django.core.management import call_command

        django.setup()
        call_command("migrate", verbosity=0)
        if not args.no_seed:
            call_command("seed_demo", "--reset", "--user", "demo", "--password", "demo-password-1")
        call_command("runserver", f"127.0.0.1:{args.port}", use_reloader=False)


if __name__ == "__main__":
    main()
