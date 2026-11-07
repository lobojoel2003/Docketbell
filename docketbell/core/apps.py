from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    name = "docketbell.core"
    label = "core"
    verbose_name = _("Court dates and reminders")

    def ready(self) -> None:
        from docketbell.core import checks  # noqa: F401  (registers system checks)
