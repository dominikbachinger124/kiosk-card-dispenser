# Kiosk Card Dispenser - Arbeitsregeln fuer den AI-Harness

## Zweck
Dieses Repository beschreibt und implementiert ein lokales MVP/Proof-of-Concept-Kiosk unter Ubuntu 24.04 LTS zur Ausgabe, Verwaltung, Aufladung und Ruecknahme von K720-Karten. Es verarbeitet Bargeldzahlungen ausschliesslich nach Bestaetigung durch Gatekeeper/Admin; es gibt keine Online-Zahlung.

## Tech-Stack
- Python 3.11 (Python >=3.11; Python 3.12 ist ebenfalls zulaessig), PySide6/QML fuer einen USB-Touchscreen.
- Qt soll Wayland oder X11 automatisch auswaehlen. Diagnose: `echo $XDG_SESSION_TYPE`.
- SQLite ueber stdlib `sqlite3`, WAL-Modus, Foreign Keys aktiviert und nummerierte SQL-Migrationen.
- `pyserial` fuer K720 ueber RS-232/USB-to-Serial; konfigurierbarer Port, bevorzugt `/dev/serial/by-id/...`.
- pytest; Ruff und mypy sind optionale Qualitaetspruefungen.
- Deutsch und Englisch, Uebersetzungen via Qt oder einfachem Dictionary; Deutsch ist Standard.

## HARTE REGELN
1. **Keine erfundenen K720-Befehle.** `hardware/k720.py` darf erst geschrieben werden, wenn `docs/k720_protocol.md` keinen Text `PLACEHOLDER` mehr enthaelt. Andernfalls STOPPEN und den Nutzer nach der echten Befehlsbeschreibung fragen. Domain, Datenbank, GUI und Fake-Hardware duerfen vorher gebaut werden. Der Pfad des Protokolls lautet exakt `docs/k720_protocol.md`.
2. **Geld ausschliesslich als Integer-Cent**, niemals als `float`. Konfigurationskonstanten in `config.toml`: `topup_cents = 2000`, `deposit_cents = 500`, `gatekeeper_collection_cents = 2500`.
3. **Ledger ist append-only.** Keine UPDATE- oder DELETE-Operationen auf Buchungen; Korrekturen erfolgen als Gegenbuchung mit nachvollziehbarem Verweis.
4. Fachlogik kennt weder Hardware noch GUI; sie arbeitet ausschliesslich mit Interfaces `CardDispenser` und `IdReader` (und service-/repository-Abstraktionen).
5. Echte Hardware ist der Betriebsmodus. `FakeDispenser` und `FakeIdReader` sind nur fuer Tests, niemals im Kiosk-Betrieb aktiv.
6. **Datensparsamkeit:** Vom Ausweis nur die Kennung (Kartennummer/UID) lesen und ausschliesslich als SHA-256-Hash mit Salt aus Config speichern. Keine weiteren Ausweisdaten speichern oder protokollieren.
7. Admin-PIN nur als Hash speichern (z.B. `hashlib.scrypt` aus der Python-Standardbibliothek oder Argon2); niemals im Klartext im Repo.
8. Keine Secrets im Repo. Lokale Konfiguration und Geheimnisse nicht committen.

## Projektstruktur
```text
src/kiosk/{domain,storage,hardware,services,gui,i18n}/
tests/
migrations/
config.toml
```
`config.toml` enthaelt nicht geheime Standardwerte; lokale Geheimnisse, Salt und PIN-Hash stammen aus einer lokalen, ignorierten Konfiguration bzw. sicheren Bereitstellung. Protokolldateien bleiben getrennt und werden nicht durch Annahmen ersetzt.

## Arbeitsweise
Arbeite die selbsttragenden Prompts strikt in Reihenfolge ab: `tasks/00-project-setup.md` bis `tasks/07-integration-and-kiosk.md`. Pro Task Tests ausfuehren und gruen bekommen, bevor zum naechsten gewechselt wird. Kleine, logisch getrennte Commits erstellen. Bei fehlenden Fachangaben fragen statt raten. Bei Protokoll-PLACEHOLDER gilt die oben genannte STOPP-Regel ausschliesslich fuer K720-Kommandocode; unabhängige Arbeiten duerfen fortgesetzt werden.

## Verbindliche Dokumentation
Vor Implementierung lesen: `docs/domain.md`, `docs/architecture.md`, `docs/ui-spec.md`, `docs/k720_protocol.md`, `docs/security-notes.md` und `docs/setup-ubuntu.md`. Fachregeln in `docs/domain.md` sind verbindlich; Abweichungen nicht stillschweigend einfuehren.
