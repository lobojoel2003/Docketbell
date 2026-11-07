"""Keep texts in memory. Used by the test suite, like Django's locmem email backend."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from docketbell.sms.backends.base import BaseBackend, SendResult

outbox: list[SentText] = []


@dataclass(frozen=True)
class SentText:
    to: str
    body: str
    provider_id: str
    callback_url: str | None = None


class LocmemBackend(BaseBackend):
    name = "locmem"

    def send(self, to: str, body: str, *, callback_url: str | None = None) -> SendResult:
        provider_id = f"locmem-{uuid.uuid4().hex[:12]}"
        outbox.append(SentText(to, body, provider_id, callback_url))
        return SendResult(provider_id=provider_id, status="sent")
