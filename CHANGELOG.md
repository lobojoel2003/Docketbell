# Changelog

All notable changes to Docketbell are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-11-07

The first public release.

### Reminders
- A welcome text when someone is signed up, then countdown reminders 7, 3 and 1 days
  before the court date (configurable with `DOCKETBELL_REMINDER_DAYS`).
- Texts go out only inside a local send window (08:00–20:00 by default), in each
  court's own time zone, and handle daylight saving changes.
- Moving a court date rebuilds the schedule and sends a short "your date changed"
  text; canceling one tells the person they don't need to go.
- After a missed court date, an optional kind follow-up asks the person to call
  before a warrant is served.
- After an outage, only the latest due reminder is sent, so nobody gets a burst of texts.
- Retries with backoff for temporary provider errors; numbers that can't receive
  texts and people who opted out at the carrier are recorded automatically.

### Two-way texting
- Reply `1` (or yes, sí, có, да, 네, نعم, wi…) to confirm; `2` (or no) to ask for help.
- `STOP`, `START` and `HELP` work as carriers expect.
- Text the name of a language ("Español", "中文", "Tiếng Việt") to switch languages.
- Anything else goes to the staff inbox, with at most one automatic "we couldn't read
  that" reply per day.

### Languages
- Every text in English, Spanish, Simplified Chinese, Vietnamese, Korean, Russian,
  Arabic and Haitian Creole, with dates and times written the local way.
- Staff dashboard in English and Spanish.
- Any text can be reworded per language from the admin without a deploy.

### Dashboard
- Upcoming court dates grouped by day, with who has confirmed, who asked for help,
  who hasn't replied and who can't be reached.
- Court date page with the full text conversation, reminder schedule and actions
  (confirm by phone, record attendance, reschedule, cancel, send a text).
- Inbox for replies that need a person.
- Messages page showing every text in every language with its SMS segment count and cost.
- Results page with appearance rates by reply.
- CSV import that is safe to re-run daily from a case management export.
- Light and dark themes, mobile layout, keyboard and screen reader friendly.

### SMS providers
- Twilio, with signed webhooks and delivery reports.
- A generic HTTP gateway protocol for local or self-hosted gateways.
- Console and in-memory backends for development and tests.

### Operations
- Docker image for the web server and worker, published to GitHub Container Registry
  with version, build number and commit baked in.
- `/healthz` and `/version.json` endpoints; the dashboard warns when the worker stops.
- `purge_old_data` for data retention, keeping a minimal record of opt-outs.
- `seed_demo` for a realistic fictional caseload.

[Unreleased]: https://github.com/lobojoel2003/Docketbell/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/lobojoel2003/Docketbell/releases/tag/v1.0.0
