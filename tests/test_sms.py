from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json

import httpx
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse

from docketbell.core.models import Message
from docketbell.sms import SMSError, get_backend
from docketbell.sms.backends.console import ConsoleBackend
from docketbell.sms.backends.http import HTTPGatewayBackend
from docketbell.sms.backends.twilio import TwilioBackend, compute_signature, is_valid_signature
from docketbell.sms.segments import analyze

# --- Segments -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "encoding", "segments"),
    [
        ("", "GSM-7", 0),
        ("a" * 160, "GSM-7", 1),
        ("a" * 161, "GSM-7", 2),
        ("a" * 306, "GSM-7", 2),
        ("a" * 307, "GSM-7", 3),
        ("€" * 80, "GSM-7", 1),  # extended characters count double
        ("€" * 81, "GSM-7", 2),
        ("¿Dónde?", "UCS-2", 1),
        ("ó" * 70, "UCS-2", 1),
        ("ó" * 71, "UCS-2", 2),
        ("It’s", "UCS-2", 1),  # a curly apostrophe forces UCS-2
        ("🙂" * 35, "UCS-2", 1),  # emoji are two UTF-16 units
    ],
)
def test_segments(text, encoding, segments):
    info = analyze(text)
    assert (info.encoding, info.segments) == (encoding, segments)


def test_segments_report_offending_characters():
    assert analyze("It’s “fine”").non_gsm == ("’", "“", "”")


# --- Backends -----------------------------------------------------------------


def test_get_backend_aliases(settings):
    assert isinstance(get_backend("console"), ConsoleBackend)
    settings.SMS_BACKEND = "console"
    assert get_backend().name == "console"


def test_console_backend_prints():
    stream = io.StringIO()
    result = ConsoleBackend(stream=stream).send("+12125550142", "Hello")
    assert result.provider_id.startswith("console-")
    assert "Hello" in stream.getvalue() and "+12125550142" in stream.getvalue()


def twilio(handler, **options):
    options.setdefault("account_sid", "AC123")
    options.setdefault("auth_token", "token")
    options.setdefault("from_number", "+12125550100")
    options.setdefault("messaging_service_sid", "")
    return TwilioBackend(transport=httpx.MockTransport(handler), **options)


def test_twilio_send():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["form"] = dict(httpx.QueryParams(request.content.decode()))
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(201, json={"sid": "SM123", "status": "queued"})

    result = twilio(handler).send("+12125550142", "Hi", callback_url="https://x/status/")
    assert result.provider_id == "SM123"
    assert seen["url"] == "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json"
    assert seen["form"] == {
        "To": "+12125550142",
        "Body": "Hi",
        "From": "+12125550100",
        "StatusCallback": "https://x/status/",
    }
    assert seen["auth"] == "Basic " + base64.b64encode(b"AC123:token").decode()


def test_twilio_messaging_service():
    form = {}

    def handler(request):
        form.update(httpx.QueryParams(request.content.decode()))
        return httpx.Response(201, json={"sid": "SM1"})

    twilio(handler, messaging_service_sid="MG1").send("+12125550142", "Hi")
    assert form["MessagingServiceSid"] == "MG1" and "From" not in form


@pytest.mark.parametrize(
    ("response", "retryable", "opted_out", "invalid"),
    [
        (httpx.Response(500), True, False, False),
        (httpx.Response(429), True, False, False),
        (httpx.Response(400, json={"code": 21610, "message": "unsubscribed"}), False, True, False),
        (httpx.Response(400, json={"code": 21211, "message": "invalid To"}), False, False, True),
        (httpx.Response(401, text="no"), False, False, False),
    ],
)
def test_twilio_errors(response, retryable, opted_out, invalid):
    with pytest.raises(SMSError) as error:
        twilio(lambda request: response).send("+12125550142", "Hi")
    assert (error.value.retryable, error.value.opted_out, error.value.invalid_number) == (
        retryable,
        opted_out,
        invalid,
    )


def test_twilio_network_errors_are_retryable():
    def timeout(request):
        raise httpx.ConnectTimeout("slow", request=request)

    def down(request):
        raise httpx.ConnectError("down", request=request)

    for handler in (timeout, down):
        with pytest.raises(SMSError) as error:
            twilio(handler).send("+12125550142", "Hi")
        assert error.value.retryable


def test_twilio_requires_credentials(settings):
    settings.TWILIO_ACCOUNT_SID = ""
    with pytest.raises(ImproperlyConfigured):
        TwilioBackend()
    with pytest.raises(ImproperlyConfigured):
        TwilioBackend(account_sid="AC1", auth_token="t", from_number="", messaging_service_sid="")


def test_twilio_signature_matches_documented_algorithm():
    url = "https://mycompany.com/myapp.php?foo=1&bar=2"
    params = {
        "CallSid": ["CA1234567890ABCDE"],
        "Caller": ["+12349013030"],
        "Digits": ["1234"],
        "From": ["+12349013030"],
        "To": ["+18005551212"],
    }
    # Twilio's documented recipe: the URL, then each POST key and value sorted by key.
    payload = (
        url
        + "CallSidCA1234567890ABCDE"
        + "Caller+12349013030"
        + "Digits1234"
        + "From+12349013030"
        + "To+18005551212"
    )
    expected = base64.b64encode(
        hmac.new(b"12345", payload.encode(), hashlib.sha1).digest()
    ).decode()
    assert compute_signature(url, params, "12345") == expected
    assert is_valid_signature(expected, ["https://other/", url], params, "12345")
    assert not is_valid_signature(expected, [url], params, "wrong")
    assert not is_valid_signature("", [url], params, "12345")


def gateway(handler, **options):
    options.setdefault("url", "https://gateway.example/send")
    options.setdefault("token", "out-token")
    return HTTPGatewayBackend(transport=httpx.MockTransport(handler), **options)


def test_gateway_send():
    seen = {}

    def handler(request):
        seen["json"] = json.loads(request.content)
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json={"id": "gw-1"})

    assert (
        gateway(handler).send("+12125550142", "Hi", callback_url="https://cb").provider_id == "gw-1"
    )
    assert seen == {
        "json": {"to": "+12125550142", "body": "Hi", "callback_url": "https://cb"},
        "auth": "Bearer out-token",
    }


def test_gateway_accepts_empty_responses():
    assert gateway(lambda r: httpx.Response(204)).send("+1", "Hi").provider_id == ""


@pytest.mark.parametrize(
    ("response", "retryable", "opted_out", "invalid"),
    [
        (httpx.Response(503), True, False, False),
        (httpx.Response(422, json={"error": "nope", "reason": "opted_out"}), False, True, False),
        (
            httpx.Response(422, json={"error": "nope", "reason": "invalid_number"}),
            False,
            False,
            True,
        ),
        (httpx.Response(400, json=["odd"]), False, False, False),
    ],
)
def test_gateway_errors(response, retryable, opted_out, invalid):
    with pytest.raises(SMSError) as error:
        gateway(lambda request: response).send("+1", "Hi")
    assert (error.value.retryable, error.value.opted_out, error.value.invalid_number) == (
        retryable,
        opted_out,
        invalid,
    )


def test_gateway_timeouts_are_retryable():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(SMSError) as error:
        gateway(handler).send("+1", "Hi")
    assert error.value.retryable


def test_gateway_requires_url(settings):
    settings.SMS_GATEWAY_URL = ""
    with pytest.raises(ImproperlyConfigured):
        HTTPGatewayBackend()


def test_backends_close_cleanly():
    backend = gateway(lambda r: httpx.Response(200, json={}))
    with backend:
        backend.send("+1", "Hi")
    assert backend._client is None
    backend = twilio(lambda r: httpx.Response(201, json={"sid": "x"}))
    with backend:
        backend.send("+1", "Hi")
    assert backend._client is None


# --- Webhooks -----------------------------------------------------------------


def signed_post(client, path, data, token="test-auth-token"):
    url = "http://testserver" + path
    signature = compute_signature(url, {k: [v] for k, v in data.items()}, token)
    return client.post(path, data, HTTP_X_TWILIO_SIGNATURE=signature)


def test_twilio_inbound_webhook(client, court_date, outbox):
    response = signed_post(
        client,
        reverse("sms:twilio-inbound"),
        {"From": "+12125550142", "Body": "1", "MessageSid": "SM9"},
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "text/xml"
    assert b"<Response>" in response.content
    court_date.refresh_from_db()
    assert court_date.confirmed_at is not None
    assert len(outbox) == 1


def test_twilio_inbound_rejects_bad_signatures(client, court_date):
    response = client.post(
        reverse("sms:twilio-inbound"),
        {"From": "+12125550142", "Body": "1"},
        HTTP_X_TWILIO_SIGNATURE="forged",
    )
    assert response.status_code == 403
    assert not Message.objects.exists()


def test_twilio_signature_check_can_be_disabled(settings, client, court_date):
    settings.TWILIO_VALIDATE_SIGNATURES = False
    response = client.post(reverse("sms:twilio-inbound"), {"From": "+12125550142", "Body": "1"})
    assert response.status_code == 200


def test_twilio_inbound_accepts_public_url_signature(client, court_date):
    path = reverse("sms:twilio-inbound")
    data = {"From": "+12125550142", "Body": "1"}
    signature = compute_signature(
        "https://reminders.example.org" + path, {k: [v] for k, v in data.items()}, "test-auth-token"
    )
    assert client.post(path, data, HTTP_X_TWILIO_SIGNATURE=signature).status_code == 200


def test_twilio_status_webhook(client, court_date):
    message = Message.objects.create(
        person=court_date.person,
        direction="out",
        phone="+1",
        body="x",
        status="sent",
        provider_id="SM5",
    )
    response = signed_post(
        client, reverse("sms:twilio-status"), {"MessageSid": "SM5", "MessageStatus": "delivered"}
    )
    assert response.status_code == 204
    message.refresh_from_db()
    assert message.status == "delivered"
    response = client.post(reverse("sms:twilio-status"), {"MessageSid": "SM5"})
    assert response.status_code == 403


def test_webhooks_reject_get(client, db):
    assert client.get(reverse("sms:twilio-inbound")).status_code == 405


AUTH = {"HTTP_AUTHORIZATION": "Bearer gateway-inbound-token"}


def test_gateway_inbound_json(client, court_date, outbox):
    response = client.post(
        reverse("sms:gateway-inbound"),
        data=json.dumps({"from": "+12125550142", "body": "2", "id": "g1"}),
        content_type="application/json",
        **AUTH,
    )
    assert response.json() == {"ok": True, "intent": "needs_help"}
    court_date.refresh_from_db()
    assert court_date.needs_help


def test_gateway_inbound_form(client, court_date):
    response = client.post(
        reverse("sms:gateway-inbound"), {"from": "+12125550142", "body": "1"}, **AUTH
    )
    assert response.json()["intent"] == "confirm"


def test_gateway_inbound_auth_and_validation(client, db):
    url = reverse("sms:gateway-inbound")
    assert client.post(url, {"from": "+1", "body": "1"}).status_code == 401
    bad = {"HTTP_AUTHORIZATION": "Bearer wrong"}
    assert client.post(url, {"from": "+1", "body": "1"}, **bad).status_code == 401
    assert client.post(url, {"body": "1"}, **AUTH).status_code == 400
    response = client.post(url, data="not json", content_type="application/json", **AUTH)
    assert response.status_code == 400


def test_gateway_status(client, court_date):
    Message.objects.create(
        person=court_date.person,
        direction="out",
        phone=court_date.person.phone,
        body="x",
        status="sent",
        provider_id="g7",
    )
    response = client.post(
        reverse("sms:gateway-status"),
        data=json.dumps({"id": "g7", "status": "undelivered", "reason": "invalid_number"}),
        content_type="application/json",
        **AUTH,
    )
    assert response.json() == {"ok": True}
    court_date.person.refresh_from_db()
    assert court_date.person.phone_status == "undeliverable"
    assert client.post(reverse("sms:gateway-status"), {"id": "g7"}).status_code == 401
