"""Central UI texts in German and English.

All user-facing strings live here. QML and ViewModels refer to keys only.
German is the default language. Missing keys fail loudly in tests, not at runtime.
"""

from __future__ import annotations

DEFAULT_LANGUAGE = "de"
SUPPORTED_LANGUAGES = ("de", "en")

TEXTS: dict[str, dict[str, str]] = {
    "de": {
        "admin.title": "Administration",
        "admin.login.prompt": "Admin-Karte auflegen und PIN eingeben",
        "admin.login.pin_label": "PIN",
        "admin.login.submit": "Anmelden",
        "admin.login.failed": "Anmeldung fehlgeschlagen.",
        "admin.login.locked": "Anmeldung vorübergehend gesperrt.",
        "admin.accounts.title": "Konten",
        "admin.accounts.empty": "Keine Konten vorhanden.",
        "admin.account.closed": "geschlossen",
        "admin.account.open": "offen",
        "admin.account.balance": "Guthaben",
        "admin.account.deposit": "Pfand",
        "admin.account.active_cards": "Ausgegebene Karten",
        "admin.account.recycled_cards": "Recycelte Karten",
        "admin.account.cancelled_cards": "Stornierte Karten",
        "admin.account.open_deposit": "Offener Pfandbetrag",
        "admin.payout.start": "Auszahlung",
        "admin.payout.warning_open_cards": (
            "Offene, nicht zurückgegebene Karten: Das Pfand wurde bereits gezahlt "
            "und kann nachträglich nicht mehr ausgezahlt werden."
        ),
        "admin.payout.ack": "Hinweis gelesen",
        "admin.payout.cash_handed_over": "Bargeld wurde übergeben",
        "admin.payout.final": "Auszahlung und Kontoschließung bestätigen",
        "admin.payout.cancel": "Abbrechen",
        "admin.payout.done": "Auszahlung abgeschlossen. Beleg: {reference}",
        "admin.payout.not_confirmed": "Bitte alle Bestätigungen setzen.",
        "admin.session.timeout": "Sitzung wegen Inaktivität beendet.",
        "admin.logout": "Abmelden",
        "error.ADMIN_AUTH_FAILED": "Anmeldung fehlgeschlagen.",
        "error.ADMIN_LOCKED": "Anmeldung vorübergehend gesperrt.",
        "error.ADMIN_SESSION_EXPIRED": "Sitzung abgelaufen. Bitte neu anmelden.",
        "error.ACCOUNT_CLOSED": "Dieses Konto ist geschlossen.",
        "error.PAYOUT_NOT_CONFIRMED": "Bitte alle Bestätigungen setzen.",
        "error.NOT_FOUND": "Konto nicht gefunden.",
        "error.KIOSK_ERROR": "Es ist ein Fehler aufgetreten.",
    },
    "en": {
        "admin.title": "Administration",
        "admin.login.prompt": "Place admin card and enter PIN",
        "admin.login.pin_label": "PIN",
        "admin.login.submit": "Log in",
        "admin.login.failed": "Login failed.",
        "admin.login.locked": "Login temporarily locked.",
        "admin.accounts.title": "Accounts",
        "admin.accounts.empty": "No accounts.",
        "admin.account.closed": "closed",
        "admin.account.open": "open",
        "admin.account.balance": "Balance",
        "admin.account.deposit": "Deposit",
        "admin.account.active_cards": "Issued cards",
        "admin.account.recycled_cards": "Recycled cards",
        "admin.account.cancelled_cards": "Cancelled cards",
        "admin.account.open_deposit": "Open deposit amount",
        "admin.payout.start": "Payout",
        "admin.payout.warning_open_cards": (
            "Open, not returned cards: the deposit was already paid and cannot "
            "be paid out later."
        ),
        "admin.payout.ack": "Warning read",
        "admin.payout.cash_handed_over": "Cash has been handed over",
        "admin.payout.final": "Confirm payout and account closure",
        "admin.payout.cancel": "Cancel",
        "admin.payout.done": "Payout completed. Receipt: {reference}",
        "admin.payout.not_confirmed": "Please set all confirmations.",
        "admin.session.timeout": "Session ended due to inactivity.",
        "admin.logout": "Log out",
        "error.ADMIN_AUTH_FAILED": "Login failed.",
        "error.ADMIN_LOCKED": "Login temporarily locked.",
        "error.ADMIN_SESSION_EXPIRED": "Session expired. Please log in again.",
        "error.ACCOUNT_CLOSED": "This account is closed.",
        "error.PAYOUT_NOT_CONFIRMED": "Please set all confirmations.",
        "error.NOT_FOUND": "Account not found.",
        "error.KIOSK_ERROR": "An error occurred.",
    },
}


def translate(key: str, language: str = DEFAULT_LANGUAGE, **values: object) -> str:
    """Return the text for ``key`` in ``language``.

    Falls back to the German text if the language is unknown, and to the key
    itself if the key is missing, so a missing text stays visible.

    Args:
        key: Stable text key such as ``admin.login.submit``.
        language: ``"de"`` or ``"en"``.
        **values: Placeholders for ``str.format``.
    """
    table = TEXTS.get(language, TEXTS[DEFAULT_LANGUAGE])
    template = table.get(key, TEXTS[DEFAULT_LANGUAGE].get(key, key))
    return template.format(**values) if values else template


__all__ = ["DEFAULT_LANGUAGE", "SUPPORTED_LANGUAGES", "TEXTS", "translate"]
