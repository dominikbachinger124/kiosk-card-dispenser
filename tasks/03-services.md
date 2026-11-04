# Task 03 - Anwendungsservices

## Ziel
Orchestriere Kartenausgabe, Aufladung, Anzeige, Recycling, Dummyzahlung, Auszahlung und automatische Erkennung transaktional ueber Domain-, Storage- und Hardware-Interfaces.

## Vorbedingungen
Tasks 00 und 01 abgeschlossen; Task 02 Interfaces verfuegbar. Lies `docs/domain.md` und `docs/architecture.md`.

## Konkrete Schritte
1. Baue einen gemeinsamen `IssueCardService` fuer erste und weitere Karte. Neue Karte verlangt Ausweis, Kontoermittlung und 24h-Cooldown-Berechnung/-Anzeige; bei Demo `cooldown_enforced=false` nur anzeigen, nicht blockieren. Weitere Karte verwendet bestehendes Konto ohne Cooldown. Beide erfordern Gatekeeper-Bestaetigung ueber 2500 Cent und buchen 2000 Guthaben + 500 Pfand, ordnen eine Karte zu und erlauben je Session nur eine Karte.
2. `TopUpService`: Ausweis, exakt 2000 Cent, Gatekeeper-Bestaetigung, append-only Buchung.
3. `ReadBalanceService` und `ReadCardService`: alle Konto-Karten einbeziehen; unbekannte Karte sofort zurueckgeben mit exakt geforderter Meldung; cancelled zurueckgeben mit geforderter Meldung.
4. `RecycleCardService`: Auswahl recycle/return, nur erfolgreich recycelte aktive Karte gibt 500 Cent Guthaben, Pfandsaldo -500, Status recycled; idempotent gegen Duplikate.
5. `DummyPaymentService`: positiver Integer-Cent-Betrag, Default 200, niemals mehr als Kontoguthaben, append-only Zahlung.
6. `AdminPayoutService`: Autorisierung durch vorab bestaetigte Admin-Identitaet/PIN-Hash, Gatekeeper-Barauszahlung, Guthaben auf null, `payout`, alle offenen Karten cancelled und Audit in atomarer DB-Transaktion. Vorab Warnung zu bereits bezahltem Pfand offener Karten bereitstellen.
7. Implementiere Wiederholungs-/Idempotenzschutz und sichere Behandlung physischer Teilfehler: nie eine Buchung behaupten, wenn Zahlung/Bestaetigung oder Hardwareerfolg fehlt. Keine Domain-Abhaengigkeit auf konkrete GUI oder Hardware.
8. Auto-Erkennung via Polling: `card_inserted` weckt Screensaver und startet ReadCard/Balance; Hardwarevorgaenge konfliktfrei serialisieren.

## Akzeptanzkriterien
Alle Betrags-/Karten-/Cooldown-/Pfand-/Auszahlungsregeln aus `docs/domain.md` umgesetzt. Fake nur injizierbar im Test. Physischer Fehler fuehrt zu sichtbarem Recovery-Status und keiner falschen Doppelbuchung. Services gut testbar ohne Qt/UI.

## Tests
pytest fuer Ausgabe neu/weitere, Cooldown Demo und enforced, Zahlung bestaetigt/abgelehnt, Aufladung, Kontostand, unbekannt/gesperrt, recycle erfolgreich/fehlgeschlagen/doppelt, Zahlung ueber Guthaben, Auszahlung/Cancellation/Audit, Transaktionsrollback und Auto-Erkennung. Gesamtsuite gruen.
