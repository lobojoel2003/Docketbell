"""Compiled catalogs must match their sources, so nobody ships stale texts."""

from __future__ import annotations

import gettext
from pathlib import Path

import polib
import pytest
from django.conf import settings

LOCALE = Path(settings.LOCALE_PATHS[0])
CATALOGS = sorted(LOCALE.glob("*/LC_MESSAGES/django.po"))


def test_every_text_language_has_a_catalog():
    folders = {path.parent.parent.name for path in CATALOGS}
    from django.utils.translation import to_locale

    expected = {to_locale(code) for code, _ in settings.DOCKETBELL_LANGUAGES if code != "en"}
    assert expected <= folders


@pytest.mark.parametrize("po_path", CATALOGS, ids=lambda p: p.parent.parent.name)
def test_mo_files_are_up_to_date(po_path):
    mo_path = po_path.with_suffix(".mo")
    assert mo_path.exists(), f"Run compilemessages: {mo_path} is missing"
    with mo_path.open("rb") as handle:
        compiled = gettext.GNUTranslations(handle)
    for entry in polib.pofile(str(po_path)).translated_entries():
        if entry.msgid_plural:
            assert compiled.ngettext(entry.msgid, entry.msgid_plural, 1) == entry.msgstr_plural[0]
        else:
            assert compiled.gettext(entry.msgid) == entry.msgstr, entry.msgid


@pytest.mark.parametrize("po_path", CATALOGS, ids=lambda p: p.parent.parent.name)
def test_catalogs_have_plural_forms_and_no_fuzzy_entries(po_path):
    catalog = polib.pofile(str(po_path))
    assert "INTEGER" not in catalog.metadata.get("Plural-Forms", "INTEGER")
    assert not catalog.fuzzy_entries()
