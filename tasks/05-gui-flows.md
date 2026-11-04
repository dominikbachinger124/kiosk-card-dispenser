# Task 05 - Nutzerablaeufe

## Ziel
Verbinde die sieben Orbit-Funktionen mit Services und setze alle Texte, Bestaetigungen und Abbruchfaelle aus `docs/ui-spec.md` um.

## Vorbedingungen
Tasks 00-04 abgeschlossen; Services und UI-Grundgeruest getestet. Lies `docs/domain.md` und `docs/ui-spec.md`.

## Konkrete Schritte
1. Flows: Neue Karte, Weitere Karte, Konto aufladen, Kontostand, Karte lesen, Karte recyceln, Bezahlen.
2. Neue Karte: Ausweis als Pflicht, Cooldownrestzeit sichtbar; bei Demo klar sagen, dass Nutzung nicht blockiert wird. Gatekeeper bestaetigt 25 EUR; erst dann ausgeben/buchen.
3. Weitere Karte: bestehendes Konto, kein Cooldown, aber identische 25-EUR-Bestaetigung und 2000+500-Cent-Zuordnung.
4. Aufladung: immer 20 EUR und Gatekeeper-Bestaetigung. Kontostand fuer alle Kontokarten.
5. Karte lesen: Hinweis exakt `Bitte Karte einfuehren`; automatische Erkennung, unbekannt/gesperrt sofort auswerfen und exakte deutsche Fehlermeldungen.
6. Recycling: User entscheidet Recyceln oder Zurueckgeben; nur erfolgreicher Recyclingvorgang gibt 5 EUR als Guthaben frei.
7. Bezahlen: Demo klar kennzeichnen, Integer-Cent, Standard 200, Guthabenpruefung.
8. Abbruch, Timeout, Hardwarefehler und Sprachwechsel lokalisieren. Keine Zahlungsbestaetigung durch Timeout/Default.

## Akzeptanzkriterien
Alle sieben Menuepunkte haben vollstaendige, nachvollziehbare Erfolgs- und Fehlerablaeufe. Keine Bestaetigung ueberspringbar; keine doppelten Serviceaufrufe oder Buchungen durch Mehrfach-Touch. Texte stimmen mit UI-Spezifikation ueberein.

## Tests
pytest fuer ViewModel-Flows mit gemockten Services/Fakes, alle Abbruchpunkte, Sprachvarianten, Doppel-Touch, unbekannte/gesperrte Karten und Gatekeeper-Ablehnung. Manuelle Touchbedienung in Deutsch/Englisch; Gesamtsuite gruen.
