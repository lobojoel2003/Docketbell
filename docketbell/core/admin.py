from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from docketbell.core import copy, services
from docketbell.core.models import (
    Court,
    CourtDate,
    Heartbeat,
    Message,
    MessageTemplate,
    Person,
    Reminder,
)

admin.site.site_header = _("Docketbell administration")
admin.site.site_title = _("Docketbell")
admin.site.index_title = _("Settings and records")


@admin.register(Court)
class CourtAdmin(admin.ModelAdmin):
    list_display = ["name", "address", "timezone", "phone", "is_active"]
    list_filter = ["is_active", "timezone"]
    search_fields = ["name", "address"]


class CourtDateInline(admin.TabularInline):
    model = CourtDate
    extra = 0
    fields = ["court", "starts_at", "room", "hearing_type", "status", "confirmed_at"]
    readonly_fields = ["confirmed_at"]
    show_change_link = True


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ["full_name", "phone", "language", "phone_status", "opted_out_at"]
    list_filter = ["language", "phone_status", ("opted_out_at", admin.EmptyFieldListFilter)]
    search_fields = ["first_name", "last_name", "phone", "external_id"]
    inlines = [CourtDateInline]


class ReminderInline(admin.TabularInline):
    model = Reminder
    extra = 0
    fields = ["kind", "send_at", "status", "attempts", "detail"]
    readonly_fields = ["kind", "send_at", "status", "attempts", "detail"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CourtDate)
class CourtDateAdmin(admin.ModelAdmin):
    list_display = ["person", "court", "starts_at", "status", "confirmed_at", "needs_help_at"]
    list_filter = ["status", "court", ("confirmed_at", admin.EmptyFieldListFilter)]
    search_fields = [
        "person__first_name",
        "person__last_name",
        "person__phone",
        "case_number",
        "external_id",
    ]
    date_hierarchy = "starts_at"
    raw_id_fields = ["person"]
    readonly_fields = ["confirmed_at", "needs_help_at", "help_resolved_at", "created_by"]
    inlines = [ReminderInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
            super().save_model(request, obj, form, change)
            services.enroll(obj)
            return
        moved = "starts_at" in form.changed_data
        new_start = obj.starts_at
        if moved:
            obj.starts_at = form.initial["starts_at"]
        super().save_model(request, obj, form, change)
        if moved:
            services.reschedule(obj, new_start)


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ["court_date", "kind", "send_at", "status", "attempts"]
    list_filter = ["status", "kind"]
    raw_id_fields = ["court_date", "message"]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["created_at", "direction", "phone", "kind", "intent", "status", "segments"]
    list_filter = ["direction", "status", "intent", "needs_attention", "backend"]
    search_fields = ["phone", "body", "provider_id"]
    raw_id_fields = ["person", "court_date"]
    date_hierarchy = "created_at"

    def has_change_permission(self, request, obj=None):
        return False  # the message log is a record; don't rewrite history


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ["kind_label", "language", "is_active", "updated_at", "updated_by"]
    list_filter = ["language", "is_active"]
    readonly_fields = ["updated_by", "default_text", "placeholders"]
    fields = ["kind", "language", "body", "is_active", "default_text", "placeholders", "updated_by"]

    def get_form(self, request, obj=None, **kwargs):
        from django import forms

        form = super().get_form(request, obj, **kwargs)
        form.base_fields["kind"].widget = forms.Select(
            choices=[(spec.kind, spec.label) for spec in copy.SPECS]
        )
        return form

    @admin.display(description=_("message"))
    def kind_label(self, obj):
        spec = copy.KINDS.get(obj.kind)
        return spec.label if spec else obj.kind

    @admin.display(description=_("built-in text"))
    def default_text(self, obj):
        if not obj or obj.kind not in copy.KINDS:
            return "-"
        from django.utils import translation

        with translation.override(obj.language):
            return str(copy.KINDS[obj.kind].text)

    @admin.display(description=_("placeholders you can use"))
    def placeholders(self, obj):
        return ", ".join(f"{{{name}}}" for name in copy.PLACEHOLDERS)

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Heartbeat)
class HeartbeatAdmin(admin.ModelAdmin):
    list_display = ["name", "seen_at", "version"]
