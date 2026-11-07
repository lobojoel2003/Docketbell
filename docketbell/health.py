"""Health and version endpoints for load balancers, uptime checks and support."""

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache

from docketbell.version import build_info


@never_cache
def healthz(request):
    """200 when the app can reach its database. Includes worker freshness for monitoring."""
    from docketbell.core.services import worker_status

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        database = "ok"
    except Exception:
        database = "unavailable"
    payload = {
        "status": "ok" if database == "ok" else "error",
        "database": database,
        **build_info().as_dict(),
    }
    if database == "ok":
        worker = worker_status()
        payload["worker"] = {
            "healthy": worker["healthy"],
            "last_seen": worker["last_seen"].isoformat() if worker["last_seen"] else None,
            "overdue_reminders": worker["overdue"],
        }
    return JsonResponse(payload, status=200 if database == "ok" else 503)


@never_cache
def version(request):
    return JsonResponse(build_info().as_dict())
