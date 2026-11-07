# Deploying Docketbell

Docketbell is two processes sharing one Postgres database:

- **web**: the staff dashboard and SMS webhooks (`gunicorn`).
- **worker**: sends reminders as they come due (`docketbell run_worker`).

Both come from the same image, `ghcr.io/lobojoel2003/docketbell`.

## With Docker Compose (one server)

```bash
curl -O https://raw.githubusercontent.com/lobojoel2003/Docketbell/main/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/lobojoel2003/Docketbell/main/.env.example
# edit .env: SECRET_KEY, ALLOWED_HOSTS, DOCKETBELL_ORG_NAME, DOCKETBELL_ORG_PHONE, SMS settings
docker compose up -d
docker compose exec web docketbell createsuperuser
```

Put a TLS-terminating proxy in front (Caddy, nginx, a cloud load balancer) and set:

```bash
BEHIND_HTTPS_PROXY=true
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
CSRF_TRUSTED_ORIGINS=https://reminders.example.org
DOCKETBELL_PUBLIC_URL=https://reminders.example.org
FORWARDED_ALLOW_IPS=*          # or your proxy's address
```

Pin a version in production with `DOCKETBELL_VERSION=1.0.0` (or `1` for automatic
minor and patch updates). The default `latest` follows the newest release.

## On a platform (Render, Fly.io, Railway, Heroku-style)

Run the image twice: once with the command `web` (expose port 8000, health check
`/healthz`) and once with `worker`. Point both at the same `DATABASE_URL`. The web
process runs migrations on start; set `MIGRATE_ON_START=false` if you prefer to run
`docketbell migrate` as a release step.

## Without containers

```bash
pip install "docketbell @ https://github.com/lobojoel2003/Docketbell/releases/download/v1.0.0/docketbell-1.0.0-py3-none-any.whl"
export DATABASE_URL=postgres://... SECRET_KEY=... STATIC_ROOT=/srv/docketbell/static
docketbell migrate
docketbell collectstatic --noinput
gunicorn docketbell.wsgi:application --bind 0.0.0.0:8000
docketbell run_worker        # as a separate service, e.g. under systemd
```

No long-running worker? Run `docketbell send_due_reminders` from cron every minute instead.

## Checklist

- [ ] `SECRET_KEY` is long and random; `DEBUG` is off.
- [ ] HTTPS everywhere; webhook URLs registered with your SMS provider.
- [ ] `DOCKETBELL_ORG_NAME` and `DOCKETBELL_ORG_PHONE` are what people should see and call.
- [ ] `TIME_ZONE` is your local zone; each court has the right time zone in the admin.
- [ ] Courts are added in the admin (`/admin/`), with addresses written the way they should appear in texts.
- [ ] The **Messages** page reads well in every language you serve.
- [ ] A test text to your own phone works end to end, including replying `1`.
- [ ] The worker is running: the dashboard shows a red banner if reminders are overdue,
      and `/healthz` reports `worker.healthy`.
- [ ] Backups of the Postgres database.
- [ ] A retention period (`DOCKETBELL_RETENTION_DAYS`) and a scheduled `docketbell purge_old_data`.

## Monitoring

`GET /healthz` returns `200` when the database is reachable, with build details and
worker freshness:

```json
{"status": "ok", "database": "ok", "version": "1.0.0", "build": "42", "commit": "1a2b3c4…",
 "worker": {"healthy": true, "last_seen": "2026-11-10T15:20:01+00:00", "overdue_reminders": 0}}
```

Alert if `worker.healthy` is false or `overdue_reminders` keeps growing.
