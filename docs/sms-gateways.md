# SMS providers and gateways

Docketbell sends texts through a pluggable backend chosen with `SMS_BACKEND`.

| `SMS_BACKEND` | Use it for |
|---|---|
| `console` | Development. Texts are printed in the worker's log. (Default.) |
| `twilio` | Twilio, the most common hosted provider. |
| `http` | Any other gateway: a carrier API, Kannel, Jasmin, an Android phone running a gateway app, a state or county system. |
| `locmem` | Tests. Texts are kept in memory. |
| `your.module.YourBackend` | Your own class (see below). |

## Twilio

1. Buy a number, or better, create a **Messaging Service** with one or more numbers.
   In the US you'll also need A2P 10DLC registration or a verified toll-free number.
2. Set:
   ```bash
   SMS_BACKEND=twilio
   TWILIO_ACCOUNT_SID=AC...
   TWILIO_AUTH_TOKEN=...
   TWILIO_MESSAGING_SERVICE_SID=MG...   # or TWILIO_FROM_NUMBER=+12125550100
   DOCKETBELL_PUBLIC_URL=https://reminders.example.org
   ```
3. In Twilio, point the number's (or Messaging Service's) **incoming message webhook**
   to `https://reminders.example.org/sms/twilio/inbound/` (HTTP POST).

Delivery reports come back to `/sms/twilio/status/` automatically when
`DOCKETBELL_PUBLIC_URL` is set. Every webhook is checked against Twilio's
`X-Twilio-Signature`. If Docketbell runs behind a proxy, set
`DOCKETBELL_PUBLIC_URL` to the exact public address Twilio calls, and
`BEHIND_HTTPS_PROXY=true`.

Twilio's Advanced Opt-Out already answers `STOP`. To avoid a second confirmation,
set `DOCKETBELL_SEND_OPT_OUT_CONFIRMATION=false`.

## Generic HTTP gateway

The `http` backend speaks a small JSON protocol. Most gateways need only a few lines of
glue code to match it.

### Sending

Docketbell sends `POST SMS_GATEWAY_URL` with `Authorization: Bearer SMS_GATEWAY_TOKEN`:

```json
{"to": "+12125550142", "body": "Hi Maria, ...", "callback_url": "https://reminders.example.org/sms/gateway/status/"}
```

| Gateway answers | Docketbell does |
|---|---|
| Any `2xx`, optionally `{"id": "abc123"}` | Records the text as sent, keeping `id` for delivery reports. |
| `429` or `5xx`, timeout, connection error | Retries later (5, then 10 minutes), up to `DOCKETBELL_MAX_ATTEMPTS`. |
| `4xx` with `{"error": "...", "reason": "opted_out"}` | Marks the person as opted out. |
| `4xx` with `{"reason": "invalid_number"}` | Marks the number as undeliverable. |
| Any other `4xx` | Records the failure; no retry. |

### Receiving replies

The gateway sends each incoming text to `POST /sms/gateway/inbound/`, with
`Authorization: Bearer SMS_GATEWAY_INBOUND_TOKEN`, as JSON or form data:

```json
{"from": "+12125550142", "body": "1", "id": "in-789"}
```

`id` is optional but recommended: Docketbell uses it to ignore retried deliveries.
The answer is `{"ok": true, "intent": "confirm"}`. Docketbell sends its own reply
through the gateway.

### Delivery reports (optional)

`POST /sms/gateway/status/` with the same token:

```json
{"id": "abc123", "status": "delivered"}
{"id": "abc123", "status": "undelivered", "reason": "invalid_number", "error": "Landline"}
```

`status` is one of `delivered`, `undelivered` or `failed`.

## Writing your own backend

```python
# myorg/sms.py
from docketbell.sms import BaseBackend, SendResult, SMSError


class MyCarrierBackend(BaseBackend):
    name = "mycarrier"

    def send(self, to: str, body: str, *, callback_url: str | None = None) -> SendResult:
        response = call_my_carrier(to, body)  # your code
        if response.temporary_failure:
            raise SMSError("Carrier busy", retryable=True)
        return SendResult(provider_id=response.id)
```

Then set `SMS_BACKEND=myorg.sms.MyCarrierBackend`. To accept replies, call
`docketbell.core.replies.handle_inbound(phone=..., body=..., provider_id=...)` from
your own webhook view.
