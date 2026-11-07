# Contributing to Docketbell

Thank you for helping people get to court. Contributions of every size are welcome:
code, translations, wording improvements and reports from the field.

## Getting set up

You need Python 3.12+ and, ideally, PostgreSQL. GNU gettext is only needed to update
translations.

```bash
git clone https://github.com/lobojoel2003/Docketbell.git
cd Docketbell
python -m venv .venv && source .venv/bin/activate
make install
make run          # http://127.0.0.1:8000 (SQLite by default)
```

In a second terminal, create a login and some fictional data:

```bash
DEBUG=true python manage.py createsuperuser
DEBUG=true python manage.py seed_demo
```

Run `make help` to see every task.

## Before you open a pull request

- `make lint` and `make test` pass. Tests use SQLite unless `DATABASE_URL` points at
  Postgres; CI runs them on Postgres.
- New behaviour has tests.
- `CHANGELOG.md` has a line under **Unreleased**.

## Changing the words people receive

The texts are the product, so changes get extra care:

1. Edit the English in `docketbell/core/copy.py`. Keep it short, plain and kind, keep
   the GSM-7 character set (straight quotes, no dashes) and never include case details.
2. Run `make messages` to update the catalogs.
3. Update every language in `docketbell/locale/*/LC_MESSAGES/django.po`, keeping
   `{placeholders}`, `1`, `2`, `STOP` and `START` exactly as they are.
4. Check the result on the **Messages** page in each language. The tests also check
   every text for placeholders, keywords and length.

## Translations

Translators don't need to write code: open a
[translation issue](https://github.com/lobojoel2003/Docketbell/issues/new?template=translation.yml)
with the corrected text, or edit the `.po` file directly. A native speaker's review of
any language is very welcome. See [docs/messages.md](docs/messages.md).

## Releases

Maintainers release with `make release VERSION=x.y.z` and then
`git push origin main vx.y.z`. GitHub Actions tests, builds and publishes everything.
See [Versioning and releases](README.md#versioning-and-releases).

## Code of conduct

Be kind and assume good faith. Harassment of any kind is not tolerated. This project
follows the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/);
report problems to the maintainer privately.
