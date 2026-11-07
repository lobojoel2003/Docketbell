from __future__ import annotations

import sys
import threading
import uuid

from docketbell.sms.backends.base import BaseBackend, SendResult


class ConsoleBackend(BaseBackend):
    """Print texts instead of sending them. The default for development."""

    name = "console"
    _lock = threading.Lock()

    def __init__(self, stream=None, **options) -> None:
        super().__init__(**options)
        self.stream = stream or sys.stdout

    def send(self, to: str, body: str, *, callback_url: str | None = None) -> SendResult:
        provider_id = f"console-{uuid.uuid4().hex[:12]}"
        with self._lock:
            self.stream.write(f"--- SMS to {to} ({provider_id}) ---\n{body}\n---\n")
            self.stream.flush()
        return SendResult(provider_id=provider_id, status="sent")
