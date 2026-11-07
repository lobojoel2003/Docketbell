# Security policy

Docketbell stores names, phone numbers and court dates of people involved in court
cases. Please treat security problems seriously and report them privately.

## Reporting a vulnerability

Use GitHub's private reporting:
**[Report a vulnerability](https://github.com/lobojoel2003/Docketbell/security/advisories/new)**.
Please don't open a public issue.

Include what you found, how to reproduce it, and what an attacker could do with it.
You should get a reply within a week. Once a fix is released, we'll credit you in the
release notes unless you'd rather stay anonymous.

## Supported versions

Security fixes go into the latest minor release. Run the newest `1.x` image
(`ghcr.io/lobojoel2003/docketbell:1`) to get them automatically.

## Running Docketbell safely

- Serve it only over HTTPS, and set `SECRET_KEY`, `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.
- Keep `TWILIO_VALIDATE_SIGNATURES=true` so forged webhooks are rejected.
- Use a long random `SMS_GATEWAY_INBOUND_TOKEN` if you use the HTTP gateway.
- Give staff their own accounts; only administrators need `is_staff`.
- Set `DOCKETBELL_RETENTION_DAYS` and run `purge_old_data` on a schedule so old records don't pile up.
- Texts never include charges or case numbers. Keep it that way if you customize them:
  phones are often shared.
