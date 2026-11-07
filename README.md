<p align="center">
  <img src="docs/images/logo.svg" width="84" height="84" alt="Docketbell logo: a bell with a check mark">
</p>

<h1 align="center">Docketbell</h1>

<p align="center">
  <strong>Court date text reminders.</strong><br>
  Short, kind, clear texts in each person's language, and a dashboard that shows at a glance who has confirmed.
</p>

<p align="center">
  <a href="https://github.com/lobojoel2003/Docketbell/actions/workflows/ci.yml"><img src="https://github.com/lobojoel2003/Docketbell/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
  <a href="https://github.com/lobojoel2003/Docketbell/releases/latest"><img src="https://img.shields.io/github/v/release/lobojoel2003/Docketbell?label=release" alt="Latest release"></a>
  <a href="https://github.com/lobojoel2003/Docketbell/pkgs/container/docketbell"><img src="https://img.shields.io/badge/docker-ghcr.io-2496ED?logo=docker&logoColor=white" alt="Docker image"></a>
  <img src="https://img.shields.io/badge/python-3.12%20%7C%203.13-3776AB?logo=python&logoColor=white" alt="Python 3.12 and 3.13">
  <img src="https://img.shields.io/badge/django-5.2%20LTS-0C4B33?logo=django&logoColor=white" alt="Django 5.2 LTS">
  <img src="https://img.shields.io/badge/texts%20in-8%20languages-f6b42c" alt="Texts in 8 languages">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/lobojoel2003/Docketbell" alt="License: AGPL-3.0"></a>
</p>

<p align="center">
  <img src="docs/images/dashboard.png" alt="Docketbell dashboard: 44% of upcoming court dates confirmed, three people asked for help, and today's court dates with each person's reply status" width="100%">
</p>

## Why

Missing a court date, often for a minor offense, can bring an arrest warrant, fines and
a suspended license. Most people who miss court forgot or misread the date, and a simple
text fixes much of that.

- In New York City in 2015, 40% of defendants, about 100,000 people, missed court for
  low-level offenses. Text reminders raised appearance by 21%. Together with a redesigned
  summons form, they led to 30,000 fewer arrest warrants over three years (study in
  *Science*, via [Phys.org](https://phys.org/news/2020-10-simple-solutions-court-no-shows-subsequent.html)).
- One in three court dates is missed, and three reminder texts cost about 3 cents per
  court date. Text and email reminders cut bench warrants by 25% in Hennepin County,
  Minnesota ([ideas42](https://www.ideas42.org/wp-content/uploads/2023/05/Effective-Communications-to-Increase-Court-Appearances_ideas42.pdf)).
- A J-PAL study found SMS reminders cut missed appearances by more than 8 percentage
  points ([J-PAL](https://www.povertyactionlab.org/evaluation/costs-failure-appear-arraignment?lang=es)).

A few states have built statewide reminder systems. Most local courts and public defender
offices have nothing, and the open-source attempts are archived or very small. Docketbell
is a complete, self-hostable system a small office can run in an afternoon.

## What it does

- **Texts people before court.** A welcome text when they're signed up, then reminders
  7, 3 and 1 days before, sent during daytime hours in the court's time zone.
- **Uses the words that work.** Every text names the day, time and place, explains
  plainly what happens if you miss court, and prompts a plan for rides, work and
  childcare ([read the copy](docs/messages.md)).
- **Speaks their language.** English, Spanish, Simplified Chinese, Vietnamese, Korean,
  Russian, Arabic and Haitian Creole, with dates written the local way. People can switch
  by texting "Español" or "中文".
- **Listens.** Reply `1` to confirm and `2` if you need help, in any language. `STOP`,
  `START` and `HELP` work as carriers expect. Questions land in a staff inbox.
- **Shows staff who's coming.** One screen shows who has confirmed, who asked for help,
  who hasn't replied and who can't be reached.
- **Follows up.** Moved dates, canceled dates and missed dates each get a short, kind text.
- **Works with your SMS provider.** Twilio out of the box, or any local gateway through a
  small HTTP protocol ([guide](docs/sms-gateways.md)).
- **Fits your workflow.** Add court dates by hand, or import a CSV export from your case
  management system every day. Re-imports are safe.
- **Measures results.** Appearance rates by reply, texts sent and cost.

## How it works

```mermaid
flowchart LR
    staff["Staff add a court date<br/>or import a CSV"] --> db[("Postgres")]
    db --> worker["Worker<br/>sends texts as they come due"]
    worker -- "welcome · 7 · 3 · 1 days before" --> phone(("Person's<br/>phone"))
    phone -- "1 · 2 · STOP · a question" --> hook["SMS webhook"]
    hook --> db
    db --> dash["Dashboard<br/>who confirmed, who needs help"]
```

Reminders are rows in Postgres with a send time. The worker claims due rows with
`SELECT … FOR UPDATE SKIP LOCKED`, so you can run several workers safely. Texts are
written at send time, so they always show the current date and place. No Redis, no
message broker, no separate scheduler.

## Screenshots

<table>
  <tr>
    <td width="50%"><img src="docs/images/conversation.png" alt="A court date page showing the reminder conversation in Spanish, the person's confirmation and the reminder schedule"><br><sub><b>Every court date has its conversation.</b> José texted "Si, ahí estaré" and was marked confirmed.</sub></td>
    <td width="50%"><img src="docs/images/messages-spanish.png" alt="The Messages page showing each Spanish text in a phone preview with its length, SMS segments and cost"><br><sub><b>Every text, in every language</b>, with its SMS segments and cost.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/images/inbox.png" alt="The inbox listing replies that need a person, such as someone who can't come because of work"><br><sub><b>The inbox</b> collects replies that need a person.</sub></td>
    <td><img src="docs/images/results.png" alt="The results page: 86% came to court; 95% of people who confirmed by text came, compared with 73% who never replied"><br><sub><b>Results</b>: appearance rates by how people replied.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/images/dashboard-dark.png" alt="The dashboard in dark mode"><br><sub>Dark mode follows the system setting.</sub></td>
    <td align="center"><img src="docs/images/dashboard-mobile.png" width="48%" alt="The dashboard on a phone"><br><sub>Works on a phone.</sub></td>
  </tr>
</table>

<sub>All names and numbers are fictional. Screenshots come from <code>make demo</code> and <code>make screenshots</code>.</sub>

## Quick start

With Docker:

```bash
git clone https://github.com/lobojoel2003/Docketbell.git
cd Docketbell
docker compose up -d
docker compose exec web docketbell createsuperuser
```

Open <http://localhost:8000>, log in, add a court in **Admin and settings → Courts**, then
add a court date. Texts are printed in the worker's log (`docker compose logs -f worker`)
until you configure an SMS provider.

Want to look around first? Load a fictional caseload:

```bash
docker compose exec web docketbell seed_demo
```

Without Docker (Python 3.12+):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
DEBUG=true python manage.py migrate
DEBUG=true python manage.py seed_demo --user demo --password demo-password-1
DEBUG=true python manage.py runserver      # http://127.0.0.1:8000, log in as demo
DEBUG=true python manage.py run_worker     # in a second terminal
```

To go live, follow the [deployment guide](docs/deployment.md).

## Configuration

Everything is set with environment variables. See [`.env.example`](.env.example).

| Variable | Default | What it does |
|---|---|---|
| `SECRET_KEY` | (required) | Django secret key. Long and random. |
| `DATABASE_URL` | SQLite file | `postgres://user:pass@host:5432/db` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Host names the site answers to. |
| `TIME_ZONE` | `America/New_York` | Default time zone. Each court can have its own. |
| `DOCKETBELL_ORG_NAME` | `Court Reminders` | Who the texts are from. |
| `DOCKETBELL_ORG_PHONE` | (none) | Number people call with questions. Appears in texts. |
| `DOCKETBELL_PUBLIC_URL` | (none) | Public address, for webhook checks and delivery reports. |
| `DOCKETBELL_REMINDER_DAYS` | `7,3,1` | Days before the court date to send reminders. `0` adds a morning-of text. |
| `DOCKETBELL_SEND_TIME` | `10:00` | Local time reminders go out. |
| `DOCKETBELL_SEND_WINDOW` | `08:00-20:00` | Nothing is sent outside these hours. |
| `DOCKETBELL_SEND_MISSED_FOLLOW_UP` | `true` | Text people who missed court, asking them to call. |
| `DOCKETBELL_RETENTION_DAYS` | `0` (keep) | Used by `purge_old_data`. |
| `DOCKETBELL_COST_PER_SEGMENT` | `0.0083` | For cost estimates on the dashboard. |
| `SMS_BACKEND` | `console` | `twilio`, `http`, `console` or a dotted path to your own backend. |
| `TWILIO_*`, `SMS_GATEWAY_*` | | Provider settings: see [SMS providers](docs/sms-gateways.md). |

`python manage.py check` warns about common mistakes, such as a send time outside the
send window, missing translations, or a missing phone number for questions.

## Importing court dates

Upload a CSV under **Import**, or run `docketbell import_court_dates dates.csv`:

```csv
first_name,last_name,phone,language,court,date,time,room,hearing_type,case_number,external_id
Maria,Lopez,(212) 555-0142,es,Main Street Courthouse,2026-12-01,9:30 AM,Courtroom 4B,Arraignment,CR-2026-0193,case-0193
```

Rows are matched by `external_id` (or by person, court and time). New dates are added,
moved dates are rescheduled and the person is told, and unchanged rows are skipped. You
can import the same nightly export again and again. Use **Check the file only** (or
`--dry-run`) to see what would happen first.

## Operations

| Command | Purpose |
|---|---|
| `docketbell run_worker` | Sends reminders as they come due. Run one or more. |
| `docketbell send_due_reminders` | The same, once, for cron. |
| `docketbell import_court_dates FILE` | CSV import. |
| `docketbell purge_old_data --days 365` | Deletes old records; keeps opt-outs so nobody is texted again. |
| `docketbell seed_demo` | A fictional caseload for training and demos. |
| `docketbell --version` | Prints version, build number and commit. |

`GET /healthz` reports database and worker health for uptime monitors. The dashboard shows
a red banner if reminders are overdue because no worker is running.

## Development

```bash
make install     # editable install with test and lint tools
make test        # pytest with coverage (uses Postgres if DATABASE_URL is set)
make lint        # ruff
make messages    # extract and compile translations (needs GNU gettext)
make demo        # demo server with fictional data at a fixed time
make help        # everything else
```

The test suite has more than 400 tests and covers 95% of the code. Every text is checked
in every language for placeholders and reply keywords, and English texts are kept within
two SMS segments. See
[CONTRIBUTING.md](CONTRIBUTING.md).

```
docketbell/
├── core/          # models, scheduling and sending, replies, message copy, CSV import
├── sms/           # SMS backends (Twilio, HTTP gateway, console) and webhooks
├── dashboard/     # staff views, forms and templates
├── locale/        # translations (.po sources and compiled .mo)
├── static/        # CSS, JS, logo (no build step)
└── settings.py    # configured entirely from environment variables
```

## Versioning and releases

Docketbell follows [Semantic Versioning](https://semver.org). The version lives in
`docketbell/__init__.py`, and changes are recorded in [CHANGELOG.md](CHANGELOG.md).

Every build is identifiable. CI passes the **version**, **build number** (the GitHub
Actions run number) and **commit** into the image. They appear in the dashboard footer,
in `/healthz`, in `/version.json` and in `docketbell --version`, for example
`Docketbell 1.0.0 (build 12, 1a2b3c4)`.

To release:

```bash
make release VERSION=1.1.0        # bumps the version, dates the changelog, commits and tags v1.1.0
git push origin main v1.1.0
```

Or skip the local tag: after pushing the version bump to `main`, open **Actions → Release →
Run workflow** and enter the version. The workflow creates the tag for you.

Either way, the **Release** workflow:

1. Checks that the version matches the code and the changelog.
2. Runs the full CI suite.
3. Publishes `ghcr.io/lobojoel2003/docketbell` tagged `1.1.0`, `1.1`, `1` and `latest`,
   with an SBOM and signed build provenance.
4. Builds the Python wheel and source package, with SHA-256 checksums.
5. Creates the GitHub release with notes from the changelog and the build details.

## CI/CD

| Workflow | When | What |
|---|---|---|
| [CI](.github/workflows/ci.yml) | Every push and pull request | Ruff lint and format, tests on Python 3.12 and 3.13 against Postgres 17, Django deploy checks, migration and translation checks, package build, Docker build and smoke test. Pushes to `main` publish `ghcr.io/lobojoel2003/docketbell:edge`. |
| [Release](.github/workflows/release.yml) | Tags `v*.*.*`, or **Run workflow** | Versioned images, Python packages and the GitHub release. |
| [CodeQL](.github/workflows/codeql.yml) | Pushes, pull requests, weekly | Security analysis of Python, JavaScript and workflows. |
| [Dependabot](.github/dependabot.yml) | Weekly | Updates for Python packages, Actions and the base image. |

## Privacy and safety

- Texts never include charges or case numbers. Phones are often shared.
- Opt-outs are honored immediately and kept even after old records are purged.
- Unknown numbers never get automatic replies.
- Webhooks are signature-checked (Twilio) or token-checked (HTTP gateway).
- Staff need an account. Every manual text records who sent it.

See [SECURITY.md](SECURITY.md) to report a vulnerability.

## Roadmap

- A JSON API for case management systems to push court dates directly
- Email reminders as a second channel
- Voice-call reminders for people without text messaging
- More languages, and native-speaker review of the existing ones
- Per-court reminder schedules

Ideas and pull requests are welcome.

## License

[GNU Affero General Public License v3.0](LICENSE). You may use, change and host
Docketbell freely. If you run a modified version for others, share your changes under
the same license.

## Acknowledgements

The message design draws on public research by [ideas42](https://www.ideas42.org/),
[J-PAL](https://www.povertyactionlab.org/) and the researchers behind the New York City
summons study published in *Science*. Thanks to
the civic tech groups whose earlier court reminder projects showed the need.
