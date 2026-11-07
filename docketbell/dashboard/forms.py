from __future__ import annotations

import datetime as dt

from django import forms
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from docketbell.core import phone as phone_utils
from docketbell.core.models import Court, CourtDate, Person


class DateInput(forms.DateInput):
    input_type = "date"


class TimeInput(forms.TimeInput):
    input_type = "time"


class CourtDateFields(forms.Form):
    court = forms.ModelChoiceField(
        label=_("Court"), queryset=Court.objects.filter(is_active=True), empty_label=None
    )
    date = forms.DateField(label=_("Date"), widget=DateInput)
    time = forms.TimeField(label=_("Time"), widget=TimeInput(format="%H:%M"))
    room = forms.CharField(label=_("Courtroom"), max_length=100, required=False)
    hearing_type = forms.CharField(label=_("Hearing type"), max_length=100, required=False)
    case_number = forms.CharField(
        label=_("Case number"),
        max_length=100,
        required=False,
        help_text=_("For staff only. Never included in texts."),
    )

    def starts_at(self) -> dt.datetime:
        court = self.cleaned_data["court"]
        return dt.datetime.combine(
            self.cleaned_data["date"], self.cleaned_data["time"], tzinfo=court.tzinfo
        )

    def clean(self):
        cleaned = super().clean()
        if (
            all(cleaned.get(k) for k in ("court", "date", "time"))
            and self.starts_at() <= timezone.now()
        ):
            raise forms.ValidationError(_("The court date must be in the future."))
        return cleaned


class CourtDateCreateForm(CourtDateFields):
    first_name = forms.CharField(label=_("First name"), max_length=100)
    last_name = forms.CharField(label=_("Last name"), max_length=100, required=False)
    phone = forms.CharField(
        label=_("Mobile phone"),
        max_length=32,
        widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "off"}),
    )
    language = forms.ChoiceField(label=_("Texts in"), choices=())
    consent = forms.BooleanField(
        label=_("This person agreed to get text reminders."),
        help_text=_("They can reply STOP at any time."),
    )

    field_order = [
        "first_name",
        "last_name",
        "phone",
        "language",
        "consent",
        "court",
        "date",
        "time",
        "room",
        "hearing_type",
        "case_number",
    ]

    def __init__(self, *args, person: Person | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.person = person
        self.fields["language"].choices = settings.DOCKETBELL_LANGUAGES
        if person is not None:
            for name in ("first_name", "last_name", "phone", "language", "consent"):
                del self.fields[name]

    def clean_phone(self):
        return phone_utils.normalize_or_raise(self.cleaned_data["phone"])

    def save(self, *, user) -> CourtDate:
        from docketbell.core import services

        person = self.person
        if person is None:
            data = self.cleaned_data
            person = Person.objects.filter(
                phone=data["phone"], first_name__iexact=data["first_name"]
            ).first()
            if person is None:
                person = Person.objects.create(
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    phone=data["phone"],
                    language=data["language"],
                )
            elif person.language != data["language"]:
                person.language = data["language"]
                person.save(update_fields=["language", "updated_at"])
        court_date = CourtDate.objects.create(
            person=person,
            court=self.cleaned_data["court"],
            starts_at=self.starts_at(),
            room=self.cleaned_data["room"],
            hearing_type=self.cleaned_data["hearing_type"],
            case_number=self.cleaned_data["case_number"],
            created_by=user,
        )
        services.enroll(court_date)
        return court_date


class CourtDateEditForm(CourtDateFields):
    notify = forms.BooleanField(
        label=_("Text the person if the date or time changes"), required=False, initial=True
    )

    def __init__(self, *args, court_date: CourtDate, **kwargs):
        local = court_date.local_starts_at
        initial = {
            "court": court_date.court,
            "date": local.date(),
            "time": local.time().replace(second=0, microsecond=0),
            "room": court_date.room,
            "hearing_type": court_date.hearing_type,
            "case_number": court_date.case_number,
            "notify": True,
        }
        super().__init__(*args, initial=initial, **kwargs)
        self.court_date = court_date

    def save(self) -> bool:
        """Save the changes. Returns True if the date moved."""
        from docketbell.core import services

        court_date = self.court_date
        court_date.court = self.cleaned_data["court"]
        court_date.room = self.cleaned_data["room"]
        court_date.hearing_type = self.cleaned_data["hearing_type"]
        court_date.case_number = self.cleaned_data["case_number"]
        court_date.save()
        new_start = self.starts_at()
        if new_start != court_date.starts_at:
            return services.reschedule(court_date, new_start, notify=self.cleaned_data["notify"])
        return False


class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ["first_name", "last_name", "phone", "language", "notes"]
        widgets = {
            "phone": forms.TextInput(attrs={"inputmode": "tel"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_phone(self):
        return phone_utils.normalize_or_raise(self.cleaned_data["phone"])

    def save(self, commit=True):
        person = super().save(commit=False)
        if "phone" in self.changed_data:
            person.phone_status = Person.PhoneStatus.OK
        if commit:
            person.save()
        return person


class TextForm(forms.Form):
    body = forms.CharField(
        label=_("Message"),
        max_length=640,
        widget=forms.Textarea(attrs={"rows": 3, "data-segment-counter": "true"}),
    )


class SimulateReplyForm(forms.Form):
    body = forms.CharField(label=_("Reply as this person"), max_length=320)


class ImportForm(forms.Form):
    file = forms.FileField(label=_("CSV file"))
    dry_run = forms.BooleanField(
        label=_("Check the file only (don't save anything)"), required=False, initial=True
    )
    notify = forms.BooleanField(
        label=_("Text people whose court date changed"), required=False, initial=True
    )

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > 5 * 1024 * 1024:
            raise forms.ValidationError(_("Files must be smaller than 5 MB."))
        try:
            return upload.read().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise forms.ValidationError(_("Save the file as CSV with UTF-8 encoding.")) from exc
