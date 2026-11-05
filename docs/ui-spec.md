# UI-Spezifikation

## Leitlinien
PySide6/QML, Vollbild auf Touchscreen unter Wayland oder X11; Qt waehlt die Plattform automatisch. Touch-Ziele gross (Richtwert mindestens 64x64 logische Pixel), ausreichender Abstand, hoher Kontrast, klare Fokus-/Aktivzustaende, keine ausschliessliche Farbcodierung. Texte in Deutsch und Englisch, Standard Deutsch. Dialoge kurz und eindeutig; keine PIN/Ausweiskennung anzeigen oder speichern.

## Screensaver und Orbit-Menue
Bei Inaktivitaet zeigt der Kiosk einen ruhigen Screensaver mit Betriebsbereitschaft. Hardware-Polling laeuft weiter, sodass Karten am Slot jederzeit erkannt werden. Touch, Tasteneingabe oder `card_inserted` wecken die Anwendung. Der Screensaver darf keinen Hardwarevorgang blockieren.

Das Hauptmenue ist ein Orbit-Design: sieben grosse, touchfreundliche Eintraege kreisen bzw. schweben animiert um einen zentralen Kiosk-Mittelpunkt. Eintraege: **Neue Karte**, **Weitere Karte**, **Konto aufladen**, **Kontostand**, **Karte lesen**, **Karte recyceln**, **Bezahlen**. Animation reduziert oder deaktiviert werden koennen; Eintraege bleiben stets lesbar und erreichbar. Status-/Hilfetext und Spracheinstellung sichtbar.

## Ablaufe

### Neue Karte
1. Auswahl -> Ausweis am Flipper Zero auflegen; Warteanzeige und Abbrechen.
2. Kennung: Die UID des vorgezeigten Chips dient als Kennung (MVP). Keine Namenseingabe.
3. Konto erkannt/neu angelegt.
4. Ausgabe-Fortschritt, dann Ausgabe und Aufschluesselung 20 EUR Guthaben + 5 EUR Pfand.
5. Fehler: klare Wiederherstellungshinweise, bei unklarem physischen Ergebnis Admin-Hilfe.

### Weitere Karte
Konto aus dem bestehenden Flow auswaehlen/identifizieren; keine Sperre. Gleiche Aufschluesselung, keine Preisabweichung.

### Konto aufladen
Ausweis lesen, 20-EUR-Festbetrag anzeigen (vorab bar am Gatekeeper bezahlt), bei Erfolg aktualisierten Kontostand zeigen. Keine Betragseingabe.

### Kontostand
Ausweis auflegen; Guthaben, Pfand-/Kartenuebersicht und Kontohistorie anzeigen. Aufstellung bezieht alle jemals ausgegebenen Karten ein und trennt aktive/offene, recycelte und gesperrte Karten.

### Karte lesen
Hinweis exakt: `Bitte Karte einfuehren`. Bei Einzug automatisch UID lesen und Status pruefen. Aktive Karte: Balance/Kontostand anzeigen. Unbekannt: sofort zurueckgeben/auswerfen und Text `Karte unbekannt. Bitte Karte entnehmen.` Gesperrt: zurueckgeben und Text `Karte gesperrt (gecancelt).` Screensaver durch Einzug aufwecken.

### Karte recyceln
Karte einfuehren; User wird gefragt, was mit Karte geschehen soll, mit Aktionen **Recyceln** und **Zurueckgeben**. Recyceln: Sicherheitshinweis, bestaetigen, K720 recycle in Sammelbehaelter; nur bei Erfolg 5 EUR Pfandgutschrift aufs Guthaben und neuen Stand zeigen. Zurueckgeben oder Fehler: keine Gutschrift.

### Bezahlen
Aktive Karte lesen, Demo/Dummy-Modus klar kennzeichnen. Betrag als ganze Cent bzw. EUR-Eingabe ohne Float-Arithmetik; Standard 200 Cent. Betrag darf nicht groesser als Guthaben sein. Bestaetigung mit Betrag und aktualisiertem Kontostand; Fehler bei unzureichendem Guthaben ohne Belastung.

## Meldungen Deutsch/Englisch

| Deutsch (Standard) | English |
|---|---|
| Bitte Karte einfuehren | Please insert card |
| Karte unbekannt. Bitte Karte entnehmen. | Unknown card. Please remove the card. |
| Karte gesperrt (gecancelt). | Card blocked (cancelled). |
| Bitte Ausweis auflegen. | Please present your ID. |
| Zahlung nicht bestaetigt. Vorgang abgebrochen. | Payment not confirmed. Operation cancelled. |
| Karte kann nicht gelesen werden. Bitte erneut versuchen. | Card could not be read. Please try again. |
| Hardware nicht erreichbar. Bitte Gatekeeper informieren. | Hardware unavailable. Please contact the Gatekeeper. |
| Guthaben reicht nicht aus. | Insufficient balance. |
| Offene, nicht zurueckgegebene Karten: Das Pfand wurde bereits gezahlt und kann nachtraeglich nicht mehr ausgezahlt werden. | Open, unreturned cards: the deposit has already been paid and cannot be refunded later. |

Dynamische Werte zentral und sicher einsetzen, niemals ungefilterte Kennungen in UI-Strings aufnehmen.

## Admin-Ansicht
Zugang: Admin-Karte (konfigurierte UID, maximal zwei) und PIN. Erst nach beidem Panel freigeben. Konto per Ausweis suchen. Zeige Guthaben, Pfandsaldo, Anzahl ausgegebener/recycelter Karten, offene Karten und offenen Betrag. Bei Auszahlung Barzahlung/Gatekeeper-Aktion bestaetigen, Warnhinweis zu offenen Karten sichtbar und explizite finale Bestaetigung fordern; alle offenen Karten werden storniert und Guthaben auf null ausgezahlt. Abschluss mit Beleg-/Vorgangsnummer ohne persoenliche Daten. Audit-Ereignisse protokollieren.

## Timeouts und Abbruch
Inaktivitaet fuehrt nach konfigurierbarer Zeit in Screensaver (Startwert 60 Sekunden). Nichtkritische Dialoge koennen nach weiterem Timeout abbrechen; niemals Zahlung/Ausgabe still bestaetigen. Hardwarepolling laeuft weiter und hat definierte Zeitlimits. Bei Abbruch Zustand sicher schliessen, nicht gebuchte Vorgangsschritte verwerfen und keine Teilbuchung erzeugen.
