# Architektur

## Schichten und Abhaengigkeitsrichtung

```text
PySide6/QML GUI -> ViewModels/Controller -> Services -> Domain
                                      Services -> Interfaces
Storage/SQLite <-> Repositories <- Services
Hardware-Adapter implementieren Interfaces; GUI und Domain importieren keine konkreten Hardwaretreiber.
```

- **Domain:** Entitaeten/Wertobjekte, Geld in Integer-Cent, Zustandsregeln und Ledgersemantik. Keine Kenntnis von Qt, SQLite oder Hardware.
- **Storage:** `sqlite3`-Verbindung, nummerierte SQL-Migrationen, Repositories und Transaktionsgrenzen. WAL und Foreign Keys bei jeder Verbindung aktivieren.
- **Hardware:** `CardDispenser` und `IdReader` Interfaces; reale Adapter und test-only Fakes. Serielle IO in einem Worker statt im GUI-Thread.
- **Services:** Anwendungsablaeufe und Orchestrierung, validieren Regeln und schreiben Buchungen transaktional.
- **GUI:** QML-Ansichten plus Python ViewModels; signalisiert Eingaben an Services und zeigt Resultate/Fehler, enthaelt keine Buchungsregeln.
- **i18n:** Deutsch als Standard, Englisch als zweite Sprache; Qt-Uebersetzung oder zentrale Dictionary-Dateien, keine verstreuten UI-Texte.

## Interfaces
Python-`Protocol`-Interfaces fuer Entkopplung. Vorgeschlagene Signaturen (Rueckgabe-/Fehlertypen beim Implementieren festlegen):

| Interface | Annahmesignaturen (vor Implementierung mit echtem Protokoll abgleichen) |
|---|---|
| `CardDispenser` | `issue_card() -> uid`, `read_card()`/`read_uid()`, `get_state()`/`poll()`, `return_card()`, `recycle_card()` |
| `IdReader` | `read_id() -> str` (Flipper Zero, seriell) |

Diese Methodennamen sind **Annahmen** und werden im Hardware-Task mit `docs/k720_protocol.md` abgeglichen; kein Protokollbefehl aus diesen Signaturen ableiten.

`IdReader` ist der **Flipper Zero** als Ausweisleser, angesprochen ueber den seriellen Port per CLI (`rfid read`, EM4100, 125 kHz). Adapter: `hardware/flipper_reader.py`. Kein USB-HID, kein PC/SC. Der Adapter liest nur die Kennung (UID), puffert die Eingabe, begrenzt Laenge und Timeout und loggt die Kennung nie im Klartext. Fake-Implementierungen duerfen nur durch Tests injiziert werden; das Betriebsprofil verlangt reale Hardware.

## Polling und Qt
Ein dedizierter Worker-Thread pollt den K720, begrenzt IO-Timeouts und emittiert Qt-Signale, darunter `card_inserted`, an den GUI-Thread. GUI-Aenderungen ausschliesslich im GUI-Thread. Worker beendet sich kontrolliert beim Herunterfahren. Ein gemeinsamer Hardware-Zugriffskoordinator verhindert, dass Auto-Erkennung und interaktive Vorgang gleichzeitig Befehle senden. Bei Karteneinzug waehrend Screensaver `card_inserted` weckt UI und startet ReadCard/Balance-Flow.

## SQLite und Schema-Skizze
`sqlite3`, WAL (`PRAGMA journal_mode=WAL`), `PRAGMA foreign_keys=ON` auf jeder Verbindung. Migrationen als aufsteigend nummerierte SQL-Dateien, z.B. `migrations/0001_initial.sql`, Migrationstransaktionen und angewandte Nummern protokollieren. Schemaentwurf:

- `accounts`: `id`, `id_hash` (unique, SHA-256 ueber Kennung+Salt), `created_at`, `closed_at`, gegebenenfalls Status.
- `cards`: `uid` (unique), `account_id` FK, `status` (`active`/`recycled`/`cancelled`), `issued_at`, `recycled_at`, `cancelled_at`.
- `ledger`: `id`, `account_id` FK, optional `card_uid` FK, `entry_type`, `amount_cents` signed Integer, `created_at`, `session_id`, `reversal_of` FK/Referenz und Grund/Metadaten ohne persoenliche Ausweisdaten. Append-only durch API und Datenbank-Schutz soweit praktikabel.
- `sessions`: `id`, `started_at`, `ended_at`, `flow`, `outcome`, nur notwendige technische Metadaten.
- `admin_audit`: `id`, Zeit, Aktion, Zielkonto-ID, Ergebnis und minimale Details; keine PIN, keine rohe Ausweiskennung.

Alle Summen integerbasiert. Salden koennen aus Ledger summiert werden; sofern Cache-Spalten eingefuehrt werden, innerhalb derselben Transaktion fortschreiben und testbar gegen Ledger abgleichen. Guthabenuntergrenze 0 per Service-Validierung sowie geeigneter DB-Constraint/Transaktion absichern. Indizes auf `accounts.id_hash`, `cards.account_id/status` und `ledger.account_id`.

## Services
Mindestens `IssueCardService` (gemeinsam fuer erste/weitere Ausgabe; Modus unterscheidet Ausweis-Pflicht bei neuer Karte von bestehendem Konto), `TopUpService`, `ReadBalanceService`, `ReadCardService`, `RecycleCardService`, `DummyPaymentService`, `AdminPayoutService`. Services nehmen Interfaces/Repositories per Konstruktor entgegen. Zahlung bestaetigt der Gatekeeper explizit; Buchung und Karten-/Kontenzuordnung transaktional/idempotent. Physischer Vorgang und DB-Commit sind keine gemeinsame ACID-Transaktion: Fehler-/Recovery-Zustand protokollieren, unklare Ausgabe nicht stillschweigend als erfolgreich buchen und Admin-Klaerung vorsehen.

## Fehlerbehandlung
Typed domain/application errors fuer unbekannte, gesperrte Karte, unzureichendes Guthaben, nicht bestaetigte Barzahlung, Hardware-Timeout/Portfehler, klemmt, DB-Fehler und ungueltigen Zustand. UI zeigt lokalisierte, verstaendliche Meldungen; Logs enthalten Fehlercode/Session-ID, niemals Ausweiskennung, PIN oder Geheimnisse. Hardwarefehler stoppen den betroffenen Flow sicher, verhindern Buchung bei unbestaetigtem/fehlgeschlagenem Vorgang und lassen Admin-Wiederherstellung zu. Stoerungen werden persistent gespeichert (`device_faults`) und bleiben offen, bis ein Admin sie quittiert. Die Quittierung ist eine Bestaetigung (Admin-Karte und PIN) und wird im Audit festgehalten; erst danach gibt der Kiosk Ausgaben frei.

## Konfiguration (Beispiel, keine Geheimnisse)

```toml
[app]
language = "de"
mode = "kiosk"

[money]
topup_cents = 2000
deposit_cents = 500
gatekeeper_collection_cents = 2500
default_payment_cents = 200

[hardware]
mode = "real"
k720_port = "/dev/serial/by-id/REPLACE_WITH_DEVICE"
serial_baudrate = 0 # Nur nach verifiziertem Protokoll ausfuellen
id_reader_device = "auto"

[admin]
admin_uids = [] # 1-2 konfigurierte UIDs lokal bereitstellen, keine Secrets committen
pin_hash = "" # ausschliesslich lokal gesalzener PIN-Hash

[privacy]
# Salt geheim und lokal bereitstellen; nicht in versionierter Beispielconfig speichern.
id_hash_salt_env = "KIOSK_ID_HASH_SALT"
```

Baudrate nicht erraten; `0` ist ein nicht betriebsbereiter Hinweiswert und muss vor echtem Start durch verifizierte Herstellerangabe ersetzt werden. `mode=real` ist einziger Betriebsmodus; Fakes sind Tests vorbehalten. Secrets zur Laufzeit aus Umgebung oder lokaler, ignorierter Config beziehen.

## Logging und Betrieb
Rotierende lokale Logs mit Zeit, Level, Modul, Session-ID und Fehlercode; keine Kennungen, UIDs soweit personenbeziehbar, PINs oder Secrets loggen. SQLite-Datei und Logs mit restriktiven Berechtigungen. Kiosk startet erst bei valider Config, initialisierten Migrationen und erreichbarer realer Hardware; andernfalls sichtbarer Fehler/Admin-Modus, kein stiller Fake-Fallback.
