"""Pluggable SMS sending.

Pick a backend with the ``SMS_BACKEND`` setting: ``console``, ``locmem``,
``twilio``, ``http`` (any gateway that speaks a small JSON protocol), or the
dotted path of your own class. See ``docs/sms-gateways.md``.
"""

from django.conf import settings
from django.utils.module_loading import import_string

from docketbell.sms.backends.base import BaseBackend, SendResult, SMSError

__all__ = ["BaseBackend", "SMSError", "SendResult", "get_backend"]


def get_backend(path: str | None = None, **options) -> BaseBackend:
    path = path or settings.SMS_BACKEND
    path = settings.SMS_BACKEND_ALIASES.get(path, path)
    return import_string(path)(**options)
