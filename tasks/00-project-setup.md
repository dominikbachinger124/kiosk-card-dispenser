# Task 00 - Projektgrundgeruest

## Ziel
Lege die wartbare Python-Projektbasis fuer Kiosk Card Dispenser an, ohne Hardwarebefehle oder Fachregeln zu erfinden.

## Vorbedingungen
Lies `CLAUDE.md`, `docs/domain.md`, `docs/architecture.md` und `docs/security-notes.md`. Respektiere alle harten Regeln.

## Konkrete Schritte
1. Erstelle `pyproject.toml` fuer Python >=3.11, Paketquelle `src/`, Runtime-Abhaengigkeiten PySide6 und pyserial, Entwicklungsabhaengigkeit pytest; Ruff/mypy optional konfigurierbar. Kein CI erforderlich.
2. Erstelle Paketstruktur `src/kiosk/{domain,storage,hardware,services,gui,i18n}/`, `tests/` und `migrations/` mit minimalen `__init__.py` wo passend.
3. Lege nicht geheime `config.toml` mit Sprache Deutsch, realem Betriebsmodus, topup 2000, deposit 500, gatekeeper collection 2500 Cent, an. Geheimnisse bleiben ausserhalb versionierter Config; `.gitignore` ignoriert `config.local.toml`, `.env`, DB und venv.
4. Richte pytest und minimale Smoke-Tests fuer Import, Config-Parsing/Validierung und Cent-Integerwerte ein. Erzeuge eine klare Start-/Entwicklungsnotiz ohne unzutreffende Hardwarebehauptungen.
5. Keine CI-Pipeline hinzufuegen. Keine Fake-Komponenten fuer den Betrieb konfigurieren.

## Akzeptanzkriterien
- Paket kann aus `src/` installiert/importiert werden.
- Konfiguration validiert Pflichtfelder und lehnt Float-Geldwerte ab.
- Keine Secrets/PINs/Salts enthalten; reale Hardware ist als Betriebsmodus vorgesehen.
- Keine erfundenen K720-Kommandos; Projektstruktur wie in `CLAUDE.md`.

## Tests
Fuehre `python -m pytest -q` aus; alle Tests muessen gruen sein. Bei Python 3.11 und 3.12 sicherstellen, dass Syntax kompatibel ist. Committe nur dieses Grundgeruest.
