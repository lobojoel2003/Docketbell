from __future__ import annotations

import datetime as dt
import uuid
from collections import Counter, OrderedDict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from docketbell.core import copy, importer, replies, services
from docketbell.core.models import (
    Court,
    CourtDate,
    Message,
    Person,
    Reminder,
    Response,
)
from docketbell.dashboard.forms import (
    CourtDateCreateForm,
    CourtDateEditForm,
    ImportForm,
    PersonForm,
    SimulateReplyForm,
    TextForm,
)
from docketbell.sms import get_backend
from docketbell.sms.segments import analyze

RESPONSE_ORDER = [Response.CONFIRMED, Response.NEEDS_HELP, Response.NO_REPLY, Response.UNREACHABLE]
RANGES = (7, 14, 30)


def _visible_reminders():
    return Prefetch(
        "reminders",
        queryset=Reminder.objects.exclude(status=Reminder.Status.CANCELED).order_by("send_at"),
        to_attr="visible_reminders",
    )


def _breakdown(court_dates) -> list[dict]:
    counts = Counter(cd.response for cd in court_dates)
    total = sum(counts.values())
    return [
        {
            "key": response.value,
            "label": response.label,
            "count": counts.get(response, 0),
            "share": round(100 * counts.get(response, 0) / total) if total else 0,
            "width": (100 * counts.get(response, 0) / total) if total else 0,
        }
        for response in RESPONSE_ORDER
    ]


@login_required
def home(request):
    now = timezone.now()
    tz = timezone.get_current_timezone()
    try:
        days = int(request.GET.get("days", 14))
    except ValueError:
        days = 14
    days = days if days in RANGES else 14
    courts = Court.objects.filter(is_active=True)
    court_id = request.GET.get("court", "")

    start_of_today = dt.datetime.combine(timezone.localtime(now, tz).date(), dt.time.min, tzinfo=tz)
    qs = (
        CourtDate.objects.with_people()
        .filter(
            status=CourtDate.Status.SCHEDULED,
            starts_at__gte=start_of_today,
            starts_at__lt=now + dt.timedelta(days=days),
        )
        .prefetch_related(_visible_reminders())
    )
    if court_id.isdigit():
        qs = qs.filter(court_id=int(court_id))
    court_dates = list(qs)

    groups: OrderedDict[dt.date, list[CourtDate]] = OrderedDict()
    for cd in court_dates:
        groups.setdefault(cd.local_starts_at.date(), []).append(cd)
    today = timezone.localtime(now, tz).date()

    filter_response = request.GET.get("response", "")
    if filter_response in Response.values:
        groups = OrderedDict(
            (day, [cd for cd in items if cd.response == filter_response])
            for day, items in groups.items()
        )
        groups = OrderedDict((d, items) for d, items in groups.items() if items)

    breakdown = _breakdown(court_dates)
    confirmed = next(b for b in breakdown if b["key"] == Response.CONFIRMED)
    week_ago = now - dt.timedelta(days=7)
    sent_week = Message.objects.filter(
        direction=Message.Direction.OUTBOUND, created_at__gte=week_ago
    ).exclude(status=Message.Status.FAILED)
    context = {
        "days": days,
        "ranges": RANGES,
        "courts": courts,
        "court_id": court_id,
        "groups": [(day, (day - today).days, items) for day, items in groups.items()],
        "total": len(court_dates),
        "breakdown": breakdown,
        "confirmed": confirmed,
        "filter_response": filter_response,
        "needs_help": [cd for cd in court_dates if cd.response == Response.NEEDS_HELP],
        "texts_this_week": sent_week.count(),
        "replies_this_week": Message.objects.filter(
            direction=Message.Direction.INBOUND, created_at__gte=week_ago
        ).count(),
    }
    return render(request, "dashboard/home.html", context)


@login_required
def court_date_list(request):
    now = timezone.now()
    qs = CourtDate.objects.with_people().prefetch_related(_visible_reminders())
    when = request.GET.get("when", "upcoming")
    if when == "past":
        qs = qs.filter(starts_at__lt=now).order_by("-starts_at")
    else:
        when = "upcoming"
        qs = qs.filter(starts_at__gte=now).order_by("starts_at")
    status = request.GET.get("status", "")
    if status in CourtDate.Status.values:
        qs = qs.filter(status=status)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(person__first_name__icontains=q)
            | Q(person__last_name__icontains=q)
            | Q(person__phone__contains="".join(ch for ch in q if ch.isdigit()) or q)
            | Q(case_number__icontains=q)
        )
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "dashboard/court_date_list.html",
        {
            "page": page,
            "when": when,
            "status": status,
            "q": q,
            "statuses": CourtDate.Status.choices,
        },
    )


@login_required
def court_date_create(request):
    person = None
    if request.GET.get("person", "").isdigit():
        person = get_object_or_404(Person, pk=int(request.GET["person"]))
    if not Court.objects.filter(is_active=True).exists():
        messages.warning(request, _("Add a court in the admin before adding court dates."))
        return redirect("admin:core_court_add")
    form = CourtDateCreateForm(request.POST or None, person=person)
    if request.method == "POST" and form.is_valid():
        court_date = form.save(user=request.user)
        messages.success(
            request,
            _("Added. %(name)s will get a welcome text, then reminders before the date.")
            % {"name": court_date.person.first_name},
        )
        return redirect("dashboard:court-date", pk=court_date.pk)
    return render(request, "dashboard/court_date_form.html", {"form": form, "person": person})


def _thread(person: Person):
    return (
        Message.objects.filter(person=person)
        .select_related("sent_by", "court_date")
        .order_by("created_at", "id")
    )


@login_required
def court_date_detail(request, pk: int):
    court_date = get_object_or_404(CourtDate.objects.with_people(), pk=pk)
    reminders = court_date.reminders.select_related("message").order_by("send_at", "id")
    thread = list(_thread(court_date.person))
    for message in thread:
        message.segment_info = analyze(message.body)
    context = {
        "cd": court_date,
        "person": court_date.person,
        "reminders": reminders,
        "thread": thread,
        "text_form": TextForm(),
        "simulate_form": SimulateReplyForm()
        if settings.DOCKETBELL_ALLOW_SIMULATED_REPLIES
        else None,
        "other_dates": court_date.person.court_dates.exclude(pk=pk).select_related("court"),
    }
    return render(request, "dashboard/court_date_detail.html", context)


@login_required
def court_date_edit(request, pk: int):
    court_date = get_object_or_404(CourtDate.objects.with_people(), pk=pk)
    form = CourtDateEditForm(request.POST or None, court_date=court_date)
    if request.method == "POST" and form.is_valid():
        moved = form.save()
        messages.success(
            request,
            _("Court date moved. Reminders were rescheduled.") if moved else _("Saved."),
        )
        return redirect("dashboard:court-date", pk=pk)
    return render(request, "dashboard/court_date_edit.html", {"form": form, "cd": court_date})


@login_required
@require_POST
def court_date_action(request, pk: int):
    court_date = get_object_or_404(CourtDate.objects.with_people(), pk=pk)
    action = request.POST.get("action")
    notify = request.POST.get("notify") == "on"
    if action == "confirm":
        services.mark_confirmed(court_date)
        messages.success(request, _("Marked as confirmed."))
    elif action == "unconfirm":
        court_date.confirmed_at = None
        court_date.save(update_fields=["confirmed_at", "updated_at"])
        messages.success(request, _("Confirmation removed."))
    elif action == "resolve_help":
        services.resolve_help(court_date)
        messages.success(request, _("Marked as handled."))
    elif action == "attended":
        services.record_outcome(court_date, CourtDate.Status.ATTENDED)
        messages.success(request, _("Recorded: came to court."))
    elif action == "missed":
        services.record_outcome(court_date, CourtDate.Status.MISSED, notify=notify)
        messages.success(
            request,
            _("Recorded: missed court. A follow-up text is on its way.")
            if notify
            else _("Recorded: missed court."),
        )
    elif action == "cancel":
        services.cancel(court_date, notify=notify)
        messages.success(request, _("Court date canceled. Pending reminders were stopped."))
    else:
        raise Http404("Unknown action")
    return redirect("dashboard:court-date", pk=pk)


@login_required
@require_POST
def court_date_text(request, pk: int):
    court_date = get_object_or_404(CourtDate.objects.with_people(), pk=pk)
    form = TextForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Write a message first."))
    elif court_date.person.is_opted_out:
        messages.error(request, _("This person opted out of texts. Call them instead."))
    else:
        outcome = services.send_manual(
            court_date.person, form.cleaned_data["body"], user=request.user, court_date=court_date
        )
        if outcome.ok:
            messages.success(request, _("Text sent."))
        else:
            messages.error(
                request,
                _("The text could not be sent: %(error)s") % {"error": outcome.message.error},
            )
    return redirect(reverse("dashboard:court-date", args=[pk]) + "#conversation")


@login_required
@require_POST
def court_date_simulate(request, pk: int):
    if not settings.DOCKETBELL_ALLOW_SIMULATED_REPLIES:
        raise Http404("Simulated replies are turned off")
    court_date = get_object_or_404(CourtDate.objects.with_people(), pk=pk)
    form = SimulateReplyForm(request.POST)
    if form.is_valid():
        with get_backend() as backend:
            message = replies.handle_inbound(
                phone=court_date.person.phone,
                body=form.cleaned_data["body"],
                provider_id=f"simulated-{uuid.uuid4().hex[:12]}",
                backend=backend,
            )
        messages.info(
            request,
            _("Simulated reply understood as: %(intent)s")
            % {"intent": message.get_intent_display()},
        )
    return redirect(reverse("dashboard:court-date", args=[pk]) + "#conversation")


@login_required
def person_list(request):
    q = request.GET.get("q", "").strip()
    qs = Person.objects.annotate(dates=Count("court_dates")).order_by("last_name", "first_name")
    if q:
        digits = "".join(ch for ch in q if ch.isdigit())
        filters = Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(external_id=q)
        if digits:
            filters |= Q(phone__contains=digits)
        qs = qs.filter(filters)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    now = timezone.now()
    for person in page:
        person.next_date = (
            person.court_dates.upcoming(now).select_related("court").order_by("starts_at").first()
        )
    return render(request, "dashboard/person_list.html", {"page": page, "q": q})


@login_required
def person_detail(request, pk: int):
    person = get_object_or_404(Person, pk=pk)
    form = PersonForm(request.POST or None, instance=person)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Saved."))
        return redirect("dashboard:person", pk=pk)
    thread = list(_thread(person))
    for message in thread:
        message.segment_info = analyze(message.body)
    return render(
        request,
        "dashboard/person_detail.html",
        {
            "person": person,
            "form": form,
            "court_dates": person.court_dates.select_related("court").order_by("-starts_at"),
            "thread": thread,
        },
    )


@login_required
def inbox(request):
    show = request.GET.get("show", "open")
    qs = Message.objects.filter(direction=Message.Direction.INBOUND).select_related(
        "person", "court_date__court", "handled_by"
    )
    if show == "all":
        qs = qs.order_by("-created_at")
    else:
        show = "open"
        qs = qs.filter(needs_attention=True, handled_at__isnull=True).order_by("-created_at")
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(request, "dashboard/inbox.html", {"page": page, "show": show})


@login_required
@require_POST
def inbox_handle(request, pk: int):
    message = get_object_or_404(Message, pk=pk, direction=Message.Direction.INBOUND)
    message.handled_at = timezone.now()
    message.handled_by = request.user
    message.save(update_fields=["handled_at", "handled_by"])
    messages.success(request, _("Marked as handled."))
    return redirect(request.POST.get("next") or "dashboard:inbox")


def _studio_language(request) -> str:
    codes = dict(settings.DOCKETBELL_LANGUAGES)
    lang = request.GET.get("lang", "")
    return lang if lang in codes else "en"


@login_required
def studio(request):
    """Every text in every language, as people will see it, with its cost."""
    language = _studio_language(request)
    sample = copy.sample_context(language)
    cost = settings.DOCKETBELL_COST_PER_SEGMENT
    groups = {"reminder": [], "reply": []}
    for spec in copy.SPECS:
        template, is_custom = copy.template_for(spec.kind, language)
        body = copy.fill(template, sample, language)
        info = analyze(body)
        groups[spec.group].append(
            {
                "spec": spec,
                "body": body,
                "info": info,
                "custom": is_custom,
                "cost": info.segments * cost,
            }
        )
    countdown = services.countdown_schedule()
    days_before: dict[str, list[int]] = {}
    for kind, days_ in countdown:
        days_before.setdefault(kind, []).append(days_)
    for item in groups["reminder"]:
        days_list = days_before.get(item["spec"].kind, [])
        item["schedule_note"] = (
            ngettext(
                "Scheduled %(days)s day before.",
                "Scheduled %(days)s days before.",
                max(days_list),
            )
            % {"days": ", ".join(str(d) for d in days_list)}
            if days_list
            else ""
        )
    typical_kinds = [copy.Kind.ENROLLMENT, *(kind for kind, _d in countdown)]
    by_kind = {item["spec"].kind: item for item in groups["reminder"]}
    typical_segments = sum(by_kind[k]["info"].segments for k in typical_kinds if k in by_kind)
    with translation.override(language):
        direction = "rtl" if translation.get_language_bidi() else "ltr"
    context = {
        "language": language,
        "languages": settings.DOCKETBELL_LANGUAGES,
        "groups": groups,
        "direction": direction,
        "typical_texts": len(typical_kinds),
        "typical_segments": typical_segments,
        "typical_cost": typical_segments * cost,
        "cost_per_segment": cost,
        "schedule": settings.DOCKETBELL_REMINDER_DAYS,
        "send_time": settings.DOCKETBELL_SEND_TIME,
    }
    return render(request, "dashboard/studio.html", context)


@login_required
def results(request):
    """Did people come to court? Broken down by how they answered the texts."""
    now = timezone.now()
    try:
        days = int(request.GET.get("days", 90))
    except ValueError:
        days = 90
    days = days if days in (30, 90, 365) else 90
    since = now - dt.timedelta(days=days)
    past = list(
        CourtDate.objects.with_people().filter(
            starts_at__gte=since,
            starts_at__lt=now,
            status__in=[CourtDate.Status.ATTENDED, CourtDate.Status.MISSED],
        )
    )

    def rate(items):
        attended = sum(1 for cd in items if cd.status == CourtDate.Status.ATTENDED)
        return {
            "total": len(items),
            "attended": attended,
            "rate": round(100 * attended / len(items)) if items else None,
        }

    overall = rate(past)
    groups = [
        {"label": _("Confirmed by text"), **rate([cd for cd in past if cd.confirmed_at])},
        {
            "label": _("Asked for help"),
            **rate([cd for cd in past if cd.needs_help_at and not cd.confirmed_at]),
        },
        {
            "label": _("Never replied"),
            **rate([cd for cd in past if not cd.confirmed_at and not cd.needs_help_at]),
        },
    ]
    outbound = Message.objects.filter(direction=Message.Direction.OUTBOUND, created_at__gte=since)
    delivered_or_sent = outbound.exclude(
        status__in=[Message.Status.FAILED, Message.Status.UNDELIVERED]
    )
    segments = sum(delivered_or_sent.values_list("segments", flat=True))
    context = {
        "days": days,
        "overall": overall,
        "groups": groups,
        "unrecorded": CourtDate.objects.filter(
            starts_at__gte=since, starts_at__lt=now, status=CourtDate.Status.SCHEDULED
        ).count(),
        "texts_sent": delivered_or_sent.count(),
        "texts_failed": outbound.count() - delivered_or_sent.count(),
        "segments": segments,
        "cost": segments * settings.DOCKETBELL_COST_PER_SEGMENT,
        "opt_outs": Person.objects.filter(opted_out_at__gte=since).count(),
        "replies": Message.objects.filter(
            direction=Message.Direction.INBOUND, created_at__gte=since
        ).count(),
    }
    return render(request, "dashboard/results.html", context)


@login_required
def import_view(request):
    report = None
    form = ImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        report = importer.import_court_dates(
            form.cleaned_data["file"],
            user=request.user,
            dry_run=form.cleaned_data["dry_run"],
            notify=form.cleaned_data["notify"],
        )
    return render(
        request,
        "dashboard/import.html",
        {
            "form": form,
            "report": report,
            "columns": importer.REQUIRED + importer.OPTIONAL,
            "required": importer.REQUIRED,
            "courts": Court.objects.filter(is_active=True),
        },
    )


@login_required
def import_template(request):
    response = HttpResponse(importer.TEMPLATE_CSV, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="docketbell-import-template.csv"'
    return response
