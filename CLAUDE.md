# Kiosk Card Dispenser - Global Rules

Status: Spezifikationsphase. Im Repo liegen Doku, Tasks und `config.toml`, noch kein Python-Code. Die Regeln unten beschreiben den Zielzustand, der in `tasks/00-project-setup.md` bis `tasks/07-integration-and-kiosk.md` entsteht. Fachregeln stehen in `docs/domain.md` und sind verbindlich.

## Zweck
Lokales MVP/Proof-of-Concept-Kiosk unter Ubuntu 24.04 LTS zur Ausgabe, Verwaltung, Aufladung und Ruecknahme von K720-Karten. Bargeld wird ausserhalb der Software vom Gatekeeper entgegengenommen und am Terminal bestaetigt. Keine Online-Zahlung, keine Cloud, kein Netzwerkzugriff fuer MVP-Funktionen.

## Verbindliche Dokumentation
Vor Implementierung lesen: `docs/domain.md`, `docs/architecture.md`, `docs/ui-spec.md`, `docs/k720_protocol.md`, `docs/security-notes.md`, `docs/setup-ubuntu.md`. Abweichungen von Fachregeln nicht stillschweigend einfuehren.

## 1. Hard Rules (binding, verbatim from project spec)
1. **Keine erfundenen K720-Befehle.** `hardware/k720.py` darf erst geschrieben werden, wenn `docs/k720_protocol.md` keinen Text `PLACEHOLDER` mehr enthaelt. Andernfalls STOPPEN und den Nutzer nach der echten Befehlsbeschreibung fragen. Domain, Datenbank, GUI und Fake-Hardware duerfen vorher gebaut werden. Der Pfad des Protokolls lautet exakt `docs/k720_protocol.md`. Die STOPP-Regel gilt nur fuer K720-Kommandocode; unabhaengige Arbeiten duerfen weitergehen.
2. **Geld ausschliesslich als Integer-Cent**, niemals als `float`. Konfigurationskonstanten in `config.toml`: `topup_cents = 2000`, `deposit_cents = 500`, `gatekeeper_collection_cents = 2500`.
3. **Ledger ist append-only.** Keine UPDATE- oder DELETE-Operationen auf Buchungen; Korrekturen als Gegenbuchung mit Verweis (`reversal_of`).
4. Fachlogik kennt weder Hardware noch GUI; sie arbeitet ausschliesslich mit Interfaces `CardDispenser` und `IdReader` sowie Service-/Repository-Abstraktionen.
5. Echte Hardware ist der Betriebsmodus. `FakeDispenser` und `FakeIdReader` sind nur fuer Tests, niemals im Kiosk-Betrieb aktiv.
6. **Datensparsamkeit:** Vom Ausweis nur die Kennung (UID) lesen; ausschliesslich als SHA-256 mit Salt aus Config speichern. Keine weiteren Ausweisdaten speichern oder protokollieren.
7. Admin-PIN nur als Hash speichern (`hashlib.scrypt` oder Argon2); niemals im Klartext im Repo.
8. Keine Secrets im Repo. `config.local.toml`, `.env`, Salt und PIN-Hash nicht committen.

## 2. Core Principles
- **Typisierung:** Jede Funktion hat vollstaendige Type Hints. `mypy --strict` gilt fuer `src/kiosk/domain` und `src/kiosk/services`.
- **Immutability:** Wertobjekte sind `@dataclass(frozen=True, slots=True)`.
- **Explizite Fehler:** Typed Exceptions aus `kiosk.domain.errors`. Keine stillen `except`-Bloecke, keine nackten `except:`.
- **Keine Geldarithmetik mit float**, keine Rundung ausserhalb der Domain.
- **Injektion statt Globals:** Services, Clock und Repositories per Konstruktor. Keine Singletons, keine modulweiten Verbindungen.
- **Fail closed:** Unklarer Hardwarezustand fuehrt nicht zu einer Buchung. Fehler werden sichtbar gemacht.
- **Kleine Commits:** Ein logischer Schritt pro Commit, Tests gruen vor dem Commit.

## 3. Tech Stack
| Bereich | Technologie | Version (Stand Recherche) | Installation |
|---|---|---|---|
| Sprache | Python | >=3.11, Entwicklung auf 3.12 (`.python-version`) | `uv python install 3.12` |
| Paketmanager | uv (`pyproject.toml` + `uv.lock`) | aktuelle uv-Version, Update via `uv self update` | Systeminstallation, nicht im Projekt |
| GUI | PySide6 (Qt for Python) mit QML | 6.12.x (PyPI: 6.12.0) | `uv add pyside6` |
| Datenbank | SQLite via stdlib `sqlite3`, WAL, `foreign_keys=ON` | stdlib | entfaellt |
| Hardware | pyserial (K720, RS-232/USB-to-Serial) | 3.5 | `uv add pyserial` |
| Tests | pytest | 9.x (PyPI: 9.2.0) | `uv add --dev pytest` |
| Lint/Format | ruff (lint + format) | 0.x (PyPI: 0.17.3) | `uv add --dev ruff` |
| Typen | mypy | 2.x (PyPI: 2.4.1) | `uv add --dev mypy` |
| Logging | stdlib `logging` mit eigenem JSON-Formatter | stdlib | entfaellt |

Exakte Versionen stehen ausschliesslich in `uv.lock`; die Tabelle dokumentiert nur den Stand bei der Recherche. Aenderungen nur ueber `uv add` bzw. `uv add --dev`, danach `uv.lock` committen. Keine zusaetzlichen Runtime-Abhaengigkeiten ohne Begruendung in der Commit-Nachricht.

- **Qt-Plattform:** Qt waehlt Wayland oder X11 automatisch. Diagnose: `echo $XDG_SESSION_TYPE`.
- **Sprachen:** Deutsch (Standard) und Englisch ueber `i18n/` (Qt-Uebersetzung oder zentrale Dictionary-Dateien). Keine verstreuten UI-Texte.

## 4. Architecture
### Layers and dependency direction
```text
gui (QML + ViewModels) -> services -> domain
services -> storage (repositories) and hardware interfaces
hardware adapters implement interfaces; domain/gui never import them
```

### Project structure
```text
pyproject.toml        uv-Projekt, src-Layout
uv.lock
.python-version       3.12
config.toml           nicht geheime Defaults
migrations/           0001_initial.sql, 0002_... (aufsteigend, nie editieren)
src/kiosk/
  domain/             Entitaeten, Money, Regeln, Fehlertypen (keine Imports aus Qt/sqlite/serial)
  storage/            Verbindung, Migrationsrunner, Repositories, Unit of Work
  hardware/           Protocols (CardDispenser, IdReader), Adapter, Worker; k720.py nur nach Protokollfreigabe
  services/           Anwendungsablaeufe, Transaktionsgrenzen
  gui/                QML-Dateien, ViewModels (QObject)
  i18n/               Uebersetzungen de/en
tests/
  domain/ storage/ services/ hardware/ gui/   spiegeln src/kiosk
  conftest.py         gemeinsame Fixtures
```

### Patterns
- **Protocol-Interfaces** fuer Hardware (`typing.Protocol`), nicht ABCs.
- **Repository pro Aggregat** ueber einer Unit of Work mit Transaktionsgrenze pro Service-Aufruf.
- **Serielle IO im Worker-Thread** (`QThread`/`QObject` mit `moveToThread`), Ergebnisse ausschliesslich per Qt-Signal an den GUI-Thread. GUI-Objekte nur im GUI-Thread veraendern.
- **Hardware-Zugriffskoordinator:** Polling und interaktive Befehle serialisieren (Lock/Queue).
- **Clock-Interface** (`now() -> datetime` in UTC) statt `datetime.now()` im Code, damit Cooldown testbar ist.

## 5. Code Style
### Naming
| Element | Konvention | Beispiel |
|---|---|---|
| Module, Funktionen, Variablen | `snake_case` | `hash_card_uid`, `balance_cents` |
| Klassen, Exceptions | `PascalCase`, Exceptions enden auf `Error` | `TopUpService`, `CardJammedError` |
| Konstanten | `UPPER_SNAKE` | `MAX_ID_LENGTH = 32` |
| Geld-Felder | Suffix `_cents`, Typ `int` | `amount_cents: int` |
| Zeitfelder | Suffix `_at`, UTC | `created_at: datetime` |
| Qt-Properties/Signals (QML-sichtbar) | `camelCase` (QML-Konvention) | `balanceCents`, `balanceChanged` |
| QML-Dateien | `PascalCase.qml` | `CardInsertedView.qml` |
| QML-Ids und Funktionen | `camelCase` | `onConfirmClicked()` |
| Tabellen, Spalten | `snake_case`, Plural fuer Tabellen | `ledger.amount_cents` |

### Python example
```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Money:
    """Monetary amount stored as integer cents."""

    cents: int

    def __post_init__(self) -> None:
        if type(self.cents) is not int:
            raise TypeError(f"cents must be int, got {type(self.cents).__name__}")

    def __add__(self, other: "Money") -> "Money":
        return Money(self.cents + other.cents)
```

### Docstrings
Google-Stil, Pflicht fuer oeffentliche Klassen und Services. Kurz, auf Englisch.
```python
def top_up(self, account_id: int, amount: Money) -> LedgerEntry:
    """Credit an account balance and append a ledger entry.

    Args:
        account_id: Target account primary key.
        amount: Positive amount to credit.

    Raises:
        InvalidAmountError: If amount is not positive.
        AccountClosedError: If the account is closed.
    """
```
Kommentare erklaeren das *Warum*, nicht das *Was*. Keine Kommentare mit Personen- oder Ausweisbezug.

### Imports and formatting
- `ruff format` und `ruff check --fix` vor jedem Commit.
- Imports: stdlib, Drittanbieter, lokal; absolute Imports ab `kiosk.`.

## 6. Logging
Stdlib `logging` mit JSON-Formatter. Rotation ueber `RotatingFileHandler`. Log-Datei und Verzeichnis mit Modus `0600`/`0700`.

### Format
Jede Zeile ist ein JSON-Objekt mit den Feldern `ts` (UTC, ISO 8601), `level`, `logger`, `event`, `session_id`, optional `error_code`, `flow`, `account_id`, `amount_cents`.

### Setup
```python
import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    _EXTRA_FIELDS = ("session_id", "error_code", "flow", "account_id", "amount_cents")

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for field in self._EXTRA_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload, ensure_ascii=False)
```

### What to log
- **Operations:** Start/Ende jedes Flows (`card_issue_started`, `card_issue_completed`), mit `session_id` und `flow`.
- **Errors:** immer mit `error_code` (z.B. `HW_TIMEOUT`, `PORT_LOST`, `CARD_JAMMED`, `DB_LOCKED`) und `exc_info` nur fuer unerwartete Fehler.
- **Key events:** Buchungen (`ledger_entry_created` mit `amount_cents`, `account_id` intern), Admin-Login-Erfolg/-Fehler (ohne PIN), Auszahlung, Migration angewandt, Hardware verbunden/verloren.

### What never to log
- Rohe Ausweis-UID oder Hashes davon, PIN, Salt, Admin-UIDs.
- Vollstaendige Config-Objekte mit Secrets.
- Serielle Rohbytes, wenn sie Kennungen enthalten koennen.

### Example
```python
logger = logging.getLogger("kiosk.services.topup")

logger.info(
    "ledger_entry_created",
    extra={"session_id": session_id, "flow": "topup", "account_id": account_id,
           "amount_cents": amount.cents},
)
logger.error(
    "card_dispense_failed",
    extra={"session_id": session_id, "error_code": "HW_TIMEOUT", "flow": "issue"},
)
```

### Frontend (QML/Python)
GUI-Fehler gehen ueber denselben Logger `kiosk.gui`. QML ruft keine Logger direkt auf; Fehler kommen als Property/Signal aus dem ViewModel und werden dort geloggt.
```python
self._log.warning(
    "touch_action_ignored",
    extra={"session_id": self._session_id, "flow": "topup", "error_code": "BUSY"},
)
```

## 7. Testing
- **Framework:** pytest 9.x. Tests laufen ohne Geraet deterministisch.
- **Structure:** `tests/<layer>/test_<module>.py`, spiegelnd zu `src/kiosk`. Testfunktionen beginnen mit `test_`, beschreiben das erwartete Verhalten.
- **Fixtures:** in `tests/conftest.py`. Datenbanken als Datei in `tmp_path` (WAL funktioniert nicht mit `:memory:`).
- **Fakes:** `FakeDispenser`, `FakeIdReader` nur in Tests, injiziert per Konstruktor.
- **Qt:** `conftest.py` setzt `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")` vor dem ersten PySide6-Import.
- **Marker:** `@pytest.mark.hardware` fuer reale Geraete, standardmaessig nicht ausgefuehrt.

### Example
```python
import pytest

from kiosk.domain.money import Money


def test_money_rejects_float() -> None:
    with pytest.raises(TypeError):
        Money(20.0)  # type: ignore[arg-type]


@pytest.mark.parametrize("cents", [0, 500, 2000])
def test_money_stores_integer_cents(cents: int) -> None:
    assert Money(cents).cents == cents
```

### Running
```bash
uv run pytest -q                       # alle Tests, Standard-Python
uv run --python 3.11 pytest -q         # Kompatibilitaet 3.11 pruefen
uv run pytest -q -m "not hardware"     # ohne reale Geraete (Standard)
```

## 8. API Contracts
Kein HTTP-API; Vertrag ist die Grenze zwischen Service-Schicht und GUI.

- **Service-Rueckgaben:** immutable DTOs (`@dataclass(frozen=True, slots=True)`) mit primitiven Typen und `int` fuer Cent. Keine ORM- oder Repository-Objekte an die GUI geben.
- **Fehler:** Service wirft `KioskError`-Subklasse mit stabilem `code: str`. ViewModel uebersetzt `code` in lokalisierten Text (`i18n`), die GUI zeigt nie Rohtext aus Exceptions.
- **ViewModel-Properties:** Geld als `int` Cent; Formatierung (`12,00 EUR`) erfolgt im ViewModel via i18n, nicht in QML-Logik.

```python
# services/dto.py
@dataclass(frozen=True, slots=True)
class BalanceView:
    account_ref: str          # nicht die UID, nur interne Kurz-Referenz
    balance_cents: int
    deposit_cents: int


# gui/viewmodels/balance.py
class BalanceViewModel(QObject):
    balanceChanged = Signal()

    @Property(int, notify=balanceChanged)
    def balanceCents(self) -> int:
        return self._balance_cents
```

Bei Aenderungen an DTOs: Services-Tests und ViewModel-Tests gemeinsam anpassen.

## 9. Common Patterns
### Service with transaction boundary
```python
class TopUpService:
    """Append a credit to the ledger inside one transaction."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork], clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def top_up(self, account_id: int, amount: Money, session_id: str) -> LedgerEntry:
        if amount.cents <= 0:
            raise InvalidAmountError("amount must be positive")
        with self._uow_factory() as uow:
            account = uow.accounts.get(account_id)
            if account.closed_at is not None:
                raise AccountClosedError(account_id)
            entry = LedgerEntry.credit(
                account_id=account_id,
                amount=amount,
                session_id=session_id,
                created_at=self._clock.now(),
            )
            uow.ledger.append(entry)  # append-only, never update
            uow.commit()
        logger.info("ledger_entry_created", extra={"session_id": session_id,
                    "flow": "topup", "account_id": account_id,
                    "amount_cents": amount.cents})
        return entry
```

### Hardware protocol (interface, names are assumptions until protocol is verified)
```python
class CardDispenser(Protocol):
    def issue_card(self) -> str: ...
    def get_state(self) -> DispenserState: ...
    def return_card(self) -> None: ...
```
Die Methodennamen sind Annahmen aus `docs/architecture.md`; sie werden mit `docs/k720_protocol.md` abgeglichen, bevor ein Adapter entsteht.

### ViewModel with worker signal
```python
class IssueViewModel(QObject):
    statusChanged = Signal(str)

    @Slot(str)
    def onCardInserted(self, uid_hash: str) -> None:
        # Runs on GUI thread; the worker only emits, never touches widgets.
        self._current = self._issue_service.start(uid_hash)
        self.statusChanged.emit("reading")
```

## 10. Development Commands
Befehle gelten nach Task 00. Vor dem Anlegen von `pyproject.toml` existieren sie noch nicht.

```bash
# Setup
uv sync                              # Abhaengigkeiten aus uv.lock installieren
uv python install 3.11 3.12          # Interpreter bereitstellen (optional)

# Run
uv run python -m kiosk               # Kiosk starten (reale Hardware erforderlich)
uv run python -m kiosk --check-config   # Config validieren, keine Hardware-Aktion

# Test
uv run pytest -q
uv run pytest -q tests/services/test_topup.py::test_name   # einzelner Test

# Quality
uv run ruff format .
uv run ruff check --fix .
uv run mypy src/kiosk/domain src/kiosk/services

# Database
uv run python -m kiosk.storage.migrate   # Migrationen anwenden (WAL, FK aktiv)

# Dependencies
uv add <package>                     # Runtime-Abhaengigkeit, aktualisiert uv.lock
uv add --dev <package>               # Entwicklungsabhaengigkeit
```

Aenderungen an `uv.lock` committen, wenn `pyproject.toml` sich aendert.

## 11. AI Coding Assistant Instructions
1. Lies `CLAUDE.md` und die unter "Verbindliche Dokumentation" genannten Dateien, bevor du Code schreibst.
2. Halte die harten Regeln (Abschnitt 1) ein; bei Konflikt mit einer Bitte: stoppen und fragen. Bei fehlenden Fachangaben fragen statt raten.
3. Arbeite die Tasks in Reihenfolge ab (`tasks/00` bis `07`). Pro Task Tests gruen, dann Commit.
4. Verwende Integer-Cent fuer Geld. Schreibe nie `float` fuer Betraege.
5. Fuege keine Buchungs-Updates oder -Deletes hinzu; Korrekturen nur als Gegenbuchung.
6. Lege keine K720-Befehle, Baudraten oder Frames fest, solange `docs/k720_protocol.md` Platzhalter enthaelt.
7. Logge niemals UIDs, PINs, Salts oder Admin-Identitaeten; nutze `error_code` und `session_id`.
8. Nutze `uv run` fuer alle Befehle; aendere Abhaengigkeiten nur mit `uv add`.
9. Fuehre `uv run ruff check .`, `uv run ruff format .` und `uv run pytest -q` vor jedem Commit aus.
10. Schreibe Code in Englisch (Bezeichner, Docstrings); UI-Texte nur ueber `i18n`, nie hart im Code oder in QML.
