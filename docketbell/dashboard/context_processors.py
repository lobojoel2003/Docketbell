from django.conf import settings

from docketbell.version import build_info


def docketbell(request):
    context = {
        "build": build_info(),
        "org_name": settings.DOCKETBELL_ORG_NAME,
        "simulated_replies": settings.DOCKETBELL_ALLOW_SIMULATED_REPLIES,
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        from docketbell.core.models import Message
        from docketbell.core.services import worker_status

        context["inbox_count"] = Message.objects.filter(
            direction=Message.Direction.INBOUND, needs_attention=True, handled_at__isnull=True
        ).count()
        context["worker"] = worker_status()
    return context
