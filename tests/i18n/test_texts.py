"""Translation tables: complete, consistent, and falling back safely."""

from __future__ import annotations

from kiosk.i18n.texts import DEFAULT_LANGUAGE, TEXTS, translate


def test_de_and_en_have_identical_keys() -> None:
    assert set(TEXTS["de"]) == set(TEXTS["en"])


def test_every_admin_error_code_has_a_text() -> None:
    from kiosk.domain import errors

    codes = {
        cls.code
        for cls in vars(errors).values()
        if isinstance(cls, type) and issubclass(cls, errors.KioskError)
    }
    admin_codes = {
        c
        for c in codes
        if c.startswith(("ADMIN_", "ACCOUNT_", "PAYOUT_", "NOT_FOUND", "KIOSK_"))
    }
    for code in admin_codes:
        assert f"error.{code}" in TEXTS["de"], code
        assert f"error.{code}" in TEXTS["en"], code


def test_default_language_is_german() -> None:
    assert DEFAULT_LANGUAGE == "de"
    assert translate("admin.logout") == "Abmelden"


def test_english_text_is_returned_for_en() -> None:
    assert translate("admin.logout", "en") == "Log out"


def test_unknown_language_falls_back_to_german() -> None:
    assert translate("admin.logout", "fr") == "Abmelden"


def test_placeholder_is_filled() -> None:
    assert translate("admin.payout.done", "en", reference="AB12") == (
        "Payout completed. Receipt: AB12"
    )


def test_missing_key_is_visible_not_silent() -> None:
    assert translate("does.not.exist") == "does.not.exist"


def test_german_texts_use_real_umlauts_not_ascii_substitutes() -> None:
    warning = TEXTS["de"]["admin.payout.warning_open_cards"]

    assert "zurückgegeben" in warning
    assert "ausgezahlt" in warning
    assert "zurueckgegeben" not in warning
