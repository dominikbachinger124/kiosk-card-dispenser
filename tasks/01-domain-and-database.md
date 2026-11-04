# Task 01 - Domain und Datenbank

## Ziel
Implementiere die fachlichen Modelle, SQLite-Speicherung, nummerierte Migrationen und unveraenderliches Ledger gemaess `docs/domain.md`.

## Vorbedingungen
Task 00 abgeschlossen und Tests gruen. Lies `docs/domain.md` und `docs/architecture.md` vollstaendig.

## Konkrete Schritte
1. Modelle/Wertobjekte fuer Konto, Karte, Kartenstatus, Ledgerbuchung, Session und Geldbetrag erstellen. Geld ausschliesslich Integer-Cent; Guthaben onder nul onmogelijk maken.
2. Erstelle nummerierte SQL-Migrationen fuer `accounts`, `cards`, `ledger`, `sessions`, `admin_audit`, Foreign Keys, Uniques, Indizes und Constraints. Aktiviere WAL und `PRAGMA foreign_keys=ON` bei jeder Verbindung.
3. Erstelle Migration-Runner mit Versionsnachverfolgung und sicherer Transaktion. Keine stillen Schemaaenderungen ausserhalb Migrationen.
4. Implementiere Repositories und atomare Unit-of-Work/Transaktionsgrenzen. Ledger-API kennt nur INSERT; keine Update/Delete-Buchungsoperationen. Korrektur als Gegenbuchung mit Ursprung/Grund.
5. Implementiere Kontoanlage anhand SHA-256 der Kennung plus konfiguriertem Salt; rohe Kennung nicht persistieren, loggen oder zurueckgeben. PIN-/Salt-Geheimnisse nicht in Beispieldaten.
6. Implementiere und teste die Saldenregeln und Buchungstypen `cash_in_topup`, `cash_in_deposit`, `recycle_refund`, `payment`, `payout`, `card_cancel`. Entsprich den Regeln fuer aktive/recycelte/cancelled Karten und Konto-Pfand.
7. Setze Transaktions-/Idempotenzschutz fuer doppelte Vorgangs-IDs, soweit fuer die Ledgeroperation noetig.

## Akzeptanzkriterien
- SQLite neu aufsetzbar und Migrationen wiederholbar/versionsicher.
- WAL und Foreign Keys nachgewiesen aktiv.
- Keine Float-Werte fuer Geld; Guthaben kann nicht negativ werden.
- Ledger append-only; Salden nachvollziehbar und Gegenbuchungen korrekt.
- Pro Nutzerkonto getrennte Pfandfuehrung; keine globalen Pfandkonten.
- Persistierte Ausweiskennung ist nur gesalzener SHA-256-Hash.

## Tests
pytest fuer Migrationen, FK/Constraints, Repository-CRUD (ausser Ledger-Mutation), Append-only, Integer-Cent, Salden, Gegenbuchungen, Kartenstatus, Duplicate-Event/Transaktion-Rollback und Hashing ohne Rohkennung. Gesamte Testsuite muss gruen sein.
