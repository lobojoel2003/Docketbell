"""Webhooks that SMS providers call: incoming texts and delivery reports."""

from __future__ import annotations

import hmac
import json
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from docketbell.core import replies, services
from docketbell.sms import get_backend
from docketbell.sms.backends import twilio

log = logging.getLogger("docketbell")

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def _twilio_urls(request: HttpRequest) -> list[str]:
    urls = [request.build_absolute_uri()]
    if settings.DOCKETBELL_PUBLIC_URL:
        urls.append(settings.DOCKETBELL_PUBLIC_URL + request.get_full_path())
    return urls


def _twilio_verified(request: HttpRequest) -> bool:
    if not settings.TWILIO_VALIDATE_SIGNATURES:
        return True
    params = {key: request.POST.getlist(key) for key in request.POST}
    return twilio.is_valid_signature(
        request.headers.get("X-Twilio-Signature", ""),
        _twilio_urls(request),
        params,
        settings.TWILIO_AUTH_TOKEN,
    )


@csrf_exempt
@require_POST
def twilio_inbound(request: HttpRequest) -> HttpResponse:
    if not _twilio_verified(request):
        log.warning("Rejected Twilio webhook with a bad signature")
        return HttpResponseForbidden("Invalid signature")
    sender = request.POST.get("From", "")
    if sender:
        with get_backend() as backend:
            replies.handle_inbound(
                phone=sender,
                body=request.POST.get("Body", ""),
                provider_id=request.POST.get("MessageSid", ""),
                backend=backend,
            )
    return HttpResponse(EMPTY_TWIML, content_type="text/xml")


@csrf_exempt
@require_POST
def twilio_status(request: HttpRequest) -> HttpResponse:
    if not _twilio_verified(request):
        return HttpResponseForbidden("Invalid signature")
    services.record_delivery(
        request.POST.get("MessageSid", ""),
        request.POST.get("MessageStatus", ""),
        error_code=request.POST.get("ErrorCode", ""),
        error=request.POST.get("ErrorMessage", ""),
        undeliverable_codes=twilio.UNDELIVERABLE_CODES,
    )
    return HttpResponse(status=204)


def _gateway_payload(request: HttpRequest) -> dict | None:
    token = settings.SMS_GATEWAY_INBOUND_TOKEN
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(supplied, token):
        return None
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body or b"{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
    return request.POST.dict()


@csrf_exempt
@require_POST
def gateway_inbound(request: HttpRequest) -> JsonResponse:
    data = _gateway_payload(request)
    if data is None:
        return JsonResponse({"error": "unauthorized"}, status=401)
    sender = str(data.get("from", "")).strip()
    if not sender:
        return JsonResponse({"error": "'from' is required"}, status=400)
    with get_backend() as backend:
        message = replies.handle_inbound(
            phone=sender,
            body=str(data.get("body", "")),
            provider_id=str(data.get("id", "")),
            backend=backend,
        )
    return JsonResponse({"ok": True, "intent": message.intent})


@csrf_exempt
@require_POST
def gateway_status(request: HttpRequest) -> JsonResponse:
    data = _gateway_payload(request)
    if data is None:
        return JsonResponse({"error": "unauthorized"}, status=401)
    message = services.record_delivery(
        str(data.get("id", "")),
        str(data.get("status", "")),
        error_code=str(data.get("reason", "")),
        error=str(data.get("error", "")),
    )
    return JsonResponse({"ok": message is not None})
