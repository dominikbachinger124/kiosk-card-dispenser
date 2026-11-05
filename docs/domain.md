# Fachliches Domänenmodell

## Zweck, Akteure und Zahlung
Das MVP dient dem lokalen Kartenkiosk. Akteure sind **User** (nutzt Karte und Kiosk) sowie **Gatekeeper/Admin** (nimmt Bargeld entgegen, bestaetigt Zahlung und verwaltet Konten). Es gibt keine Online-Zahlung. Die Software nimmt kein Bargeld an und behauptet keine automatische Zahlungserkennung.

Der Gatekeeper kassiert bei jeder Kartenausgabe bar **25 EUR = 2500 Cent je Karte**. Das Geld wird physisch beim Gatekeeper abgegeben. Die Software bucht es auf zwei getrennte Konten pro Nutzer:
- **Guthabenkonto:** 2000 Cent je Karte (`cash_in_topup`), verfuegbar fuer Zahlungen.
- **Fundkonto:** 500 Cent je Karte (`cash_in_deposit`), das Pfand fuer die Karte. Es ist kein verfuegbares Guthaben.

Die Konten sind getrennte Kontensalden aus getrennten Ledgerbuchungen. Geld wird intern ausschliesslich als Integer-Cent gerechnet.

## Konten und Ausweiskennung
- Pro Nutzer genau ein Konto; Wiedererkennung erfolgt ueber den Hash der Ausweiskennung (Kartennummer/UID). Keine sonstigen Ausweisdaten erfassen.
- Ausweis-Einlesen ist Pflicht fuer **Neue Karte**, **Konto aufladen**, **Kontostand** und Admin-Kontosuche. **Weitere Karte** verwendet das bereits gewaehlte/bekannte Konto und verlangt keinen erneuten Cooldown-Check; vor Durchfuehrung muss das Konto im Flow eindeutig ausgewaehlt bzw. durch den erforderlichen Gatekeeper-Schritt bestaetigt sein.
- Guthaben kann sinken, jedoch nie negativ werden. Pro Konto gibt es ein Guthabenkonto und ein Fundkonto, nicht einen globalen Fundtopf. Das Fundkonto wird pro Nutzer gefuehrt, um Missbrauch durch konto-/kartenuebergreifende Verrechnung zu verhindern.
- Fund +500 je ausgegebener Karte (neue oder weitere Karte). Guthaben +2000 je ausgegebener Karte.
- Bei jedem Recycling einer dem Nutzer gehoerenden, registrierten Karte wandern 500 Cent vom Fundkonto auf das Guthabenkonto (`recycle_refund`). Die Karte wird auf `recycled` gesetzt.
- Die Auszahlung des Restguthabens erfolgt nur ueber den Admin (siehe Admin und Auszahlung). Sie ist unabhaengig vom Recycling-Ablauf des Nutzers.

## Karten und Status
Jede K720-Karte hat eine UID, ist einem Konto zugeordnet und hat einen der Statuswerte `active`, `recycled` oder `cancelled` (gesperrt). Der Statuswechsel und seine Ursache werden nachvollziehbar gespeichert. Recycelte und stornierte Karten duerfen nicht als aktive Zahlungsmittel verwendet werden.

- **Unbekannte Karte:** sofort an User zurueckgeben/auswerfen; Anzeige exakt: `Karte unbekannt. Bitte Karte entnehmen.` Keine Kontobuchung.
- **Gesperrte Karte:** an User zurueckgeben; Anzeige exakt: `Karte gesperrt (gecancelt).` Keine Belastung.
- Eine Karte ist offen, wenn sie ausgegeben und weder recycelt noch storniert ist. Kontoauswertungen unterscheiden ausgegebene, recycelte und offene Karten.

## Orbit-Menue: sieben Eintraege
Das Hauptmenue bietet genau diese sieben Funktionen: **Neue Karte**, **Weitere Karte**, **Konto aufladen**, **Kontostand**, **Karte lesen**, **Karte recyceln**, **Bezahlen**.

### Neue Karte
1. Ausweis einlesen (Pflicht), Kennung hashen und Konto finden oder anlegen.
2. Cooldown seit letzter Ausgabe derselben Ausweiskennung berechnen (24 Stunden).
3. `cooldown_enforced=false` im MVP-Demo-Modus: verbleibende Zeit wird sichtbar angezeigt, die Nutzung wird jedoch nicht blockiert. Bei aktivierter Erzwingung wird waehrend der 24 Stunden nicht ausgegeben.
4. Gatekeeper bestaetigt am Terminal, dass 25 EUR bar kassiert wurden. Ohne Bestaetigung kein Ausgabe-/Buchungsvorgang.
5. Karte ausgeben, UID dem Konto zuordnen und 2000 Cent Guthaben plus 500 Cent Pfand buchen.
6. Pro Session ist genau eine Karte erlaubt. Bei Fehlern Buchungen und Zuordnung transaktional konsistent halten; physische Teilerfolge protokollieren und Admin-Klaerung ermoeglichen.

### Weitere Karte
Eigener Orbit-Eintrag. Aus bestehendem Konto heraus kann der Nutzer ohne Cooldown-Pruefung eine weitere Karte beziehen. Es gilt **derselbe Preis** wie bei der ersten: Gatekeeper bestaetigt 25 EUR bar, wovon 2000 Cent Guthaben und 500 Cent Pfand gebucht werden. Karte dem selben Konto zuordnen. Keine Preisermässigung und kein Cooldown. Pro Session weiterhin nur eine Karte.

### Konto aufladen
Eigener Orbit-Eintrag. Ausweis lesen und Konto bestimmen. Aufladung ist immer genau **20 EUR = 2000 Cent**. Der Gatekeeper bestaetigt die Barzahlung; erst danach wird `cash_in_topup` gebucht. Kein frei waehlbarer Betrag.

### Kontostand
Ausweis auflegen/einlesen; den Kontostand des zugeordneten Kontos anzeigen, einschliesslich des aktuellen Guthabens und geeigneter Pfand-/Karteninformationen. Es umfasst alle jemals ausgegebenen Karten dieses Kontos; Kartenhistorie mindestens nach Status unterscheiden.

### Karte lesen
Hinweis exakt: `Bitte Karte einfuehren`. Gelesene aktive Karte identifiziert das Konto; Guthaben und relevanter Karten-/Kontostatus werden angezeigt. Unbekannte oder gesperrte Karte gemaess den obigen Regeln sofort zurueckgeben.

### Karte recyceln
User wird gefragt, was mit der Karte geschehen soll. Bei **Recyceln** wird die Karte vom K720 eingezogen und in den Sammelbehaelter recycelt. Nur bei erfolgreichem Recycling einer aktiven Karte werden 500 Cent vom Fundkonto auf das Guthabenkonto gebucht (`recycle_refund`), das Fundkonto sinkt um 500 und die Karte wird `recycled`. Nicht recycelbare Karte erzeugt keine Gutschrift. Doppeltes Recycling darf nicht erneut gutschreiben. (Eine Rueckgabe-Option behaelt die Karte beim User und loest keine Gutschrift aus.)

### Bezahlen (Demo/Dummy)
Karte im K720 ist das Zahlungsmittel. Demo-Abbuchung eines beliebigen, vom Flow eingegebenen Integer-Cent-Betrags; Standard z.B. 200 Cent. Betrag muss positiv sein und darf das verfuegbare Guthaben nicht uebersteigen. Bei Erfolg append-only `payment`-Buchung. Kein negativer Kontostand. Als Demo-Funktion klar kennzeichnen.

## Automatische Kartenerkennung
K720 nimmt jederzeit Karten am Slot an, auch waehrend des Screensavers. Software pollt den Automatenzustand. Wird Karteneinzug erkannt, beginnt automatisch der Ablauf **Karte lesen/Kontostand anzeigen** und der Screensaver wird geweckt. Andere Menueablaeufe duerfen dadurch nicht in einen widerspruechlichen Hardwarezustand geraten; Vorgang serialisieren und Status anzeigen.

## Admin und Auszahlung
Zugang nur mit einer konfigurierten Admin-Karte (UID, eine bis zwei Eintraege in Config) **und** PIN. Admin-Panel erlaubt Konto per Ausweis zu suchen und zeigt Guthaben, Pfandsaldo, Anzahl ausgegebener und recycelter Karten, offene Karten sowie offenen Betrag. Offener Betrag ist als noch offener Pfandbetrag der nicht recycelten, nicht stornierten Karten nachvollziehbar auszuweisen.

Auszahlung erfolgt bar durch Gatekeeper. Vor Auszahlung die Auszahlung am Terminal bestaetigen lassen; dann wird verfuegbares Guthaben auf 0 gesetzt und ein `payout`-Ledgerposten erzeugt. Beim Auszahlen/Konto-Abschluss werden **alle offenen Karten des Kontos gecancelt** (`cancelled`); es ist keine Rueckzahlung ihres bereits kassierten Pfands moeglich. Admin muss vor Bestaetigung den Warnhinweis sehen: **Offene, nicht zurueckgegebene Karten: Das Pfand wurde bereits gezahlt und kann nachtraeglich nicht mehr ausgezahlt werden.** Pfand-Auszahlung ist nur fuer recycelte Karten moeglich, deren Pfand bereits als Guthaben gebucht wurde; dieses Guthaben kann im Rahmen der normalen Auszahlung ausgezahlt werden. Kontoabschluss/Auszahlung und Kartenstornierungen muessen atomar und auditierbar sein.

## Ledger, Transaktionen und Integritaet
Ledger-Eintragstypen mindestens: `cash_in_topup`, `cash_in_deposit`, `recycle_refund`, `payment`, `payout`, `card_cancel`. Buchungen sind append-only, jede Korrektur ist eine Gegenbuchung mit Bezug auf Ursprung und Grund. Keine Buchung aendern/loeschen. Salden muessen konsistent und transaktional aus Buchungen abgeleitet oder gegen diese verifizierbar sein. SQLite-Transaktionen schuetzen zusammmengehoerige Operationen; Guthaben darf nie unter null gehen. Wiederholte UI-/Hardware-Ereignisse duerfen keine Doppelbuchungen verursachen.

## Konfigurationsstandardwerte
`topup_cents=2000`, `deposit_cents=500`, `gatekeeper_collection_cents=2500`, `cooldown_hours=24`, `cooldown_enforced=false`. Werte in Cent, keine Float-Konvertierung. Produktionsaenderungen muessen mit Domänenregeln konsistent bleiben.

## Offene Punkte
Keine.
