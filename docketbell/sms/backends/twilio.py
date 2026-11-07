"""Twilio backend, using the REST API directly (no SDK dependency).

Settings: ``TWILIO_ACCOUNT_SID``, ``TWILIO_AUTH_TOKEN`` and either
``TWILIO_MESSAGING_SERVICE_SID`` (recommended) or ``TWILIO_FROM_NUMBER``.
Point the number's incoming-message webhook at ``/sms/twilio/inbound/``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Mapping

import httpx
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from docketbell.sms.backends.base import BaseBackend, SendResult, SMSError

API_BASE = "https://api.twilio.com/2010-04-01"

# https://www.twilio.com/docs/api/errors
OPTED_OUT_CODES = frozenset({"21610"})
INVALID_NUMBER_CODES = frozenset({"21211", "21214", "21217", "21407", "21408", "21614", "21612"})
# Delivery errors that mean the number can't receive texts.
UNDELIVERABLE_CODES = frozenset({"30003", "30005", "30006"}) | INVALID_NUMBER_CODES


class TwilioBackend(BaseBackend):
    name = "twilio"
    status_callback_url_name = "sms:twilio-status"

    def __init__(self, *, transport: httpx.BaseTransport | None = None, **options) -> None:
        super().__init__(**options)
        self.account_sid = options.get("account_sid", settings.TWILIO_ACCOUNT_SID)
        self.auth_token = options.get("auth_token", settings.TWILIO_AUTH_TOKEN)
        self.from_number = options.get("from_number", settings.TWILIO_FROM_NUMBER)
        self.messaging_service_sid = options.get(
            "messaging_service_sid", settings.TWILIO_MESSAGING_SERVICE_SID
        )
        if not (self.account_sid and self.auth_token):
            raise ImproperlyConfigured("Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.")
        if not (self.messaging_service_sid or self.from_number):
            raise ImproperlyConfigured("Set TWILIO_MESSAGING_SERVICE_SID or TWILIO_FROM_NUMBER.")
        self._transport = transport
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=API_BASE,
                auth=(self.account_sid, self.auth_token),
                timeout=httpx.Timeout(10.0, connect=5.0),
                transport=self._transport,
                headers={"User-Agent": "Docketbell"},
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def send(self, to: str, body: str, *, callback_url: str | None = None) -> SendResult:
        data = {"To": to, "Body": body}
        if self.messaging_service_sid:
            data["MessagingServiceSid"] = self.messaging_service_sid
        else:
            data["From"] = self.from_number
        if callback_url:
            data["StatusCallback"] = callback_url
        try:
            response = self.client.post(f"/Accounts/{self.account_sid}/Messages.json", data=data)
        except httpx.TimeoutException as exc:
            raise SMSError("Twilio did not answer in time", retryable=True) from exc
        except httpx.TransportError as exc:
            raise SMSError(f"Could not reach Twilio: {exc}", retryable=True) from exc

        if response.status_code == 429 or response.status_code >= 500:
            raise SMSError(f"Twilio returned HTTP {response.status_code}", retryable=True)
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code >= 400:
            code = str(payload.get("code") or "")
            message = payload.get("message") or f"HTTP {response.status_code}"
            raise SMSError(
                f"Twilio error {code}: {message}" if code else f"Twilio error: {message}",
                code=code,
                opted_out=code in OPTED_OUT_CODES,
                invalid_number=code in INVALID_NUMBER_CODES,
            )
        return SendResult(provider_id=str(payload.get("sid", "")), status="sent")


def compute_signature(url: str, params: Mapping[str, list[str]], auth_token: str) -> str:
    """Twilio's request signature: HMAC-SHA1 of the URL plus sorted POST params."""
    payload = url
    for key in sorted(params):
        for value in sorted(set(params[key])):
            payload += key + value
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def is_valid_signature(
    signature: str, urls: list[str], params: Mapping[str, list[str]], auth_token: str
) -> bool:
    if not signature or not auth_token:
        return False
    return any(
        hmac.compare_digest(compute_signature(url, params, auth_token), signature) for url in urls
    )
