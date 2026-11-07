from django import template
from django.utils import dateformat, timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from docketbell.core.phone import display

register = template.Library()

# Inline SVG icons (16px, stroke-based). Status icons pair with a text label so
# colour never carries meaning on its own.
ICONS = {
    "check": '<path d="M3.5 8.5l3 3 6-7"/>',
    "alert": '<path d="M8 4.5v4"/><path d="M8 11.2v.3"/>',
    "dots": '<path d="M4.5 8h.01M8 8h.01M11.5 8h.01"/>',
    "slash": '<path d="M4.5 4.5l7 7"/>',
    "clock": '<circle cx="8" cy="8" r="5.5"/><path d="M8 5v3.2l2 1.3"/>',
    "send": '<path d="M2.5 8h9M8 4.5L11.5 8 8 11.5"/>',
    "x": '<path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/>',
    "skip": '<path d="M4 8h8"/>',
    "plus": '<path d="M8 3.5v9M3.5 8h9"/>',
    "inbox": ('<path d="M2.5 9.5h3l1 1.5h3l1-1.5h3"/><path d="M3.5 4h9l1 5.5v3h-11v-3z"/>'),
    "phone": '<path d="M5 2.5h6v11H5z"/><path d="M7.3 11.5h1.4"/>',
    "globe": (
        '<circle cx="8" cy="8" r="5.5"/>'
        '<path d="M2.5 8h11M8 2.5c2 2 2 9 0 11M8 2.5c-2 2-2 9 0 11"/>'
    ),
    "calendar": '<path d="M3 4.5h10v8.5H3z"/><path d="M3 7h10M6 3v2.5M10 3v2.5"/>',
    "upload": '<path d="M8 11V3.5M5 6.5l3-3 3 3"/><path d="M3 11.5v1.5h10v-1.5"/>',
    "bell": '<path d="M4.5 11V7.5a3.5 3.5 0 0 1 7 0V11l1 1h-9z"/><path d="M7 13.5h2"/>',
    "chart": '<path d="M3 13h10"/><path d="M5 11V8M8 11V5M11 11V7"/>',
    "people": (
        '<circle cx="6" cy="6" r="2.2"/><path d="M2.5 12.5c.5-2 2-3 3.5-3s3 1 3.5 3"/>'
        '<path d="M10.5 4.5a2 2 0 0 1 0 3.6M11.5 9.8c1 .4 1.8 1.3 2 2.7"/>'
    ),
    "message": '<path d="M2.5 3.5h11v7.5H7l-3 2.5V11H2.5z"/>',
}

RESPONSE_ICONS = {
    "confirmed": "check",
    "needs_help": "alert",
    "no_reply": "dots",
    "unreachable": "slash",
}

REMINDER_ICONS = {
    "pending": "clock",
    "sent": "check",
    "failed": "x",
    "skipped": "skip",
    "canceled": "skip",
}


@register.simple_tag
def icon(name: str, css: str = ""):
    paths = ICONS.get(name, "")
    return format_html(
        '<svg class="icon {}" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" '
        'focusable="false">{}</svg>',
        css,
        mark_safe(paths),
    )


@register.filter
def response_icon(key: str) -> str:
    return RESPONSE_ICONS.get(str(key), "dots")


@register.filter
def reminder_icon(status: str) -> str:
    return REMINDER_ICONS.get(str(status), "clock")


@register.filter
def court_time(court_date, fmt: str = "g:i A"):
    """Format a court date's start in the court's own time zone."""
    return dateformat.format(court_date.local_starts_at, fmt)


@register.filter
def in_court_tz(value, court):
    """Format-ready datetime in a court's time zone (use with |date inside {% localtime off %})."""
    if value is None:
        return value
    return timezone.localtime(value, court.tzinfo)


@register.filter
def phone(value: str) -> str:
    return display(value)


@register.filter
def money(value) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    if amount < 1:
        return f"{amount * 100:.1f}¢"
    return f"${amount:,.2f}"


@register.simple_tag(takes_context=True)
def query(context, **kwargs):
    """Current query string with some parameters replaced."""
    params = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    params.pop("page", None) if "page" not in kwargs else None
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"
