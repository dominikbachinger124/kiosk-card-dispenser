# Task 02 - Hardware-Layer

## Ziel
Entkopple Hardware ueber Interfaces, stelle test-only Fakes bereit und implementiere reale Adapter nur auf belegter Protokollbasis.

## Vorbedingungen
Task 00 und 01 abgeschlossen, Tests gruen. Lies `docs/architecture.md`, `docs/security-notes.md` und `docs/k720_protocol.md`.

## Konkrete Schritte
1. **ZUERST** pruefen, ob `docs/k720_protocol.md` noch `PLACEHOLDER` enthaelt.
2. Interfaces `CardDispenser` und `IdReader` als Python Protocols definieren, an Architektur und benoetigte Serviceablaeufe anpassen. Methodennamen sind Annahmen; keine Annahme ist ein Hardwarebefehl.
3. `FakeDispenser` und `FakeIdReader` ausschliesslich in Testkontext implementieren. Sicherstellen, dass App-Betriebsprofil sie nicht aktivieren kann.
4. ~~`HidIdReader` (USB-HID)~~ gestrichen: Ausweisleser ist der Flipper Zero (`FlipperIdReader`), kein USB-HID (CLAUDE.md).
5. Wenn Protokolldatei noch `PLACEHOLDER` enthaelt: **STOPP fuer `K720Dispenser` und alle seriellen Kommandos.** Nur Interfaces, Fakes, HID-Reader und unabhaengige Tests bauen; Nutzer nach der echten Protokollbeschreibung fragen. Keine Befehle, Baudrate, Statuscodes oder Frames raten.
6. Nur wenn alle Platzhalter durch vollstaendige, echte Herstellerangaben ersetzt sind: `K720Dispenser` mit pyserial exakt nach `docs/k720_protocol.md` implementieren. Verifizierte Parameter, IO-Timeouts, definierte Fehlertypen und sichere Recovery nutzen; keine zusaetzlichen Befehle erfinden.
7. Polling-Worker fuer Hardwarezustand erstellen, der `card_inserted` via Qt-Signal emittiert und kontrolliert beendet werden kann. Serielle Befehle serialisieren.

## Akzeptanzkriterien
- Domain/GUI importieren keine konkreten Hardwaretreiber.
- Fake nur in Tests; realer Betrieb schlaegt sichtbar fehl, statt auf Fake zurueckzufallen.
- ID-Leser begrenzt Puffer/Timeout und leakt keine Kennung.
- Bei verbliebenem Platzhalter existiert kein K720-Kommandocode; Task wird fuer reale Hardware als blockiert dokumentiert.
- Bei vollstaendigem Protokoll entspricht jeder gesendete Befehl nachweisbar einer Herstellerangabe.

## Tests
pytest fuer Fake-Tests, Interface-Konformitaet, HID-Puffer/Timeout und Polling-/Signalpfad. Hardware-Szenarien explizit abdecken: unbekannte Karte, klemmende Karte, serieller Port weg/Timeout. Tests ohne Geraet muessen deterministisch sein. Reale Hardwaretests nur mit verifiziertem Protokoll und manueller Abnahme.
