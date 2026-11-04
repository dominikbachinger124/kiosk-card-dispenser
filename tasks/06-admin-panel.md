# Task 06 - Admin-Panel

## Ziel
Implementiere geschuetzten Adminzugang, Kontoabfrage, Auszahlungs-/Abschlussablauf und Audit gemaess Domänenregeln.

## Vorbedingungen
Tasks 00-05 abgeschlossen. Lies `docs/domain.md`, `docs/security-notes.md` und `docs/ui-spec.md`.

## Konkrete Schritte
1. Adminzugang erfordert konfigurierte Admin-Karte (ein bis zwei UIDs) plus PIN; Hash vergleichen, PIN nie speichern/loggen. Begrenze Fehlversuche und gib generische Fehlermeldung.
2. Konto per Ausweis suchen; nur Hash der Kennung verwenden. Zeige Guthaben, Pfandsaldo, ausgegebene/recycelte Karten, offene Karten und offenen Betrag.
3. Auszahlung bar: Gatekeeper bestaetigt Auszahlung, Admin bestaetigt bewusst den Abschluss. Guthaben wird auf null gebucht (`payout`), alle offenen Karten werden cancelled. Transaktional und idempotent.
4. Vor finaler Aktion Warnhinweis deutlich anzeigen: Pfand offener, nicht zurueckgegebener Karten wurde bereits gezahlt und kann nicht nachtraeglich ausgezahlt werden. Nur recycelte Karten haben Pfand bereits dem Guthaben gutgeschrieben.
5. Schreibe minimale, manipulationssichtbare `admin_audit`-Ereignisse fuer Erfolg/Fehler, Auszahlung, Abschluss und Kartenstornierung; keine Ausweiskennung, PIN oder Secrets.
6. Lokalisierung Deutsch/Englisch, sichere Logout-/Timeout-Funktion.

## Akzeptanzkriterien
Ohne Admin-Karte und korrekte PIN kein Zugriff. Keine Klartext-PIN/Identitaet in DB/Logs. Anzeigen stimmen mit Ledger/Kartenstatus ueberein; Warnung vor Geldbewegung sichtbar. Auszahlung und Storno konsistent, wiederholter Aufruf erzeugt keine Doppelbuchung.

## Tests
pytest fuer Authentisierung, Fehlversuche, Konto-KPIs, Warnung, bestaetigte/abgelehnte Auszahlung, offene Kartenstorno, Pfandbehandlung, Audit-Minimierung, Timeout und atomaren Rollback. Gesamtsuite gruen.
