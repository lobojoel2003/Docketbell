"""Generic HTTP gateway backend for local or self-hosted SMS gateways.

Many courts and legal aid groups already have an SMS gateway (an Android phone
running a gateway app, Kannel, Jasmin, a carrier API). This backend speaks a
small JSON protocol, so a few lines of glue connect any of them.

Outbound: ``POST SMS_GATEWAY_URL`` with ``Authorization: Bearer SMS_GATEWAY_TOKEN``::

    {"to": "+12125550123", "body": "Hi Maria, ...", "callback_url": "https://.../sms/gateway/status/"}

Any 2xx response means accepted. An optional JSON body ``{"id": "abc123"}``
gives the gateway's message ID for delivery reports.

See ``docs/sms-gateways.md`` for the inbound and delivery-report webhooks.
"""

from __future__ import annotations

import httpx
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from docketbell.sms.backends.base import BaseBackend, SendResult, SMSError


class HTTPGatewayBackend(BaseBackend):
    name = "http"
    status_callback_url_name = "sms:gateway-status"

    def __init__(self, *, transport: httpx.BaseTransport | None = None, **options) -> None:
        super().__init__(**options)
        self.url = options.get("url", settings.SMS_GATEWAY_URL)
        self.token = options.get("token", settings.SMS_GATEWAY_TOKEN)
        self.timeout = float(options.get("timeout", settings.SMS_GATEWAY_TIMEOUT))
        if not self.url:
            raise ImproperlyConfigured("Set SMS_GATEWAY_URL to use the HTTP gateway backend.")
        self._transport = transport
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            headers = {"User-Agent": "Docketbell", "Accept": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._client = httpx.Client(
                timeout=self.timeout, headers=headers, transport=self._transport
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def send(self, to: str, body: str, *, callback_url: str | None = None) -> SendResult:
        payload = {"to": to, "body": body}
        if callback_url:
            payload["callback_url"] = callback_url
        try:
            response = self.client.post(self.url, json=payload)
        except httpx.TimeoutException as exc:
            raise SMSError("SMS gateway did not answer in time", retryable=True) from exc
        except httpx.TransportError as exc:
            raise SMSError(f"Could not reach SMS gateway: {exc}", retryable=True) from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise SMSError(f"SMS gateway returned HTTP {response.status_code}", retryable=True)
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if response.status_code >= 400:
            error = str(data.get("error") or f"HTTP {response.status_code}")
            reason = str(data.get("reason") or "")
            raise SMSError(
                f"SMS gateway refused the text: {error}",
                code=reason,
                opted_out=reason == "opted_out",
                invalid_number=reason == "invalid_number",
            )
        return SendResult(provider_id=str(data.get("id", "")), status="sent")
