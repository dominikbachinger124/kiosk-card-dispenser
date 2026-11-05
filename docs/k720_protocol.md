# K720 Protokoll - Implementierungsgrundlage

Zweck: Diese Datei beschreibt das Verhalten des TTCE-K720 RF-Kartenausgabegeräts so, dass eine Implementierung in Python (Treiber in `device/`) ohne Rückfragen möglich ist. Verifiziert am Gerät `TTCE_K720_V104`, Adresse 0.

Quelle der Befehlsnamen und Bitwerte: SDK-Protokolldokument (`Communication Protocol of K720&k730&k750.doc`). Bei Widersprüchen zum Handbuch gilt das SDK. Das Handbuch wird nur für Statusbeschreibungen herangezogen.

## 1. Serielle Verbindung

- 9600 Baud, 8 Datenbits, keine Parität, 1 Stoppbit. Halbduplex.
- Port als Konfiguration (`/dev/ttyUSB0` unter Linux, `COMx` unter Windows), nie fest codiert.
- Zugriff unter Linux über Gruppe `dialout`.

## 2. Rahmen (Frame)

| Byte(s)      | Bedeutung                                       |
|--------------|-------------------------------------------------|
| `0x02`       | STX                                             |
| ADDH, ADDL   | Geräteadresse als ASCII-Ziffern `"00"`..`"15"`  |
| LEN_H, LEN_L | Länge der Nutzlast, Big-Endian                  |
| Nutzlast     | Befehlscode und Parameter                       |
| `0x03`       | ETX                                             |
| BCC          | XOR aller Bytes von STX bis ETX einschließlich  |

Beispiel für `AP` an Adresse 0: `02 30 30 00 02 41 50 03 BCC`.

Die 7-Byte-Variante ohne LEN aus dem Handbuch wird NICHT verwendet.

## 3. Handshake

Für alle Befehle gleich:

1. Host sendet den Befehlsrahmen.
2. Gerät antwortet mit `ACK 0x06 ADDH ADDL` (angenommen) oder `NAK 0x15 ADDH ADDL` (Formatfehler).
3. Host sendet `ENQ 0x05 ADDH ADDL`. **Pflicht.** Ohne ENQ führt das Gerät den Befehl nicht aus. Das wurde für `DC`, `FC*`, `CP` und `RS` gemessen.
4. Gerät antwortet nur bei Abfragen mit einem Antwortrahmen:
   - `AP`, `RF`, `GV`, `0x3B xx`: Antwortrahmen.
   - Bewegungsbefehle (`DC`, `FC*`, `CP`, `RS`, `BE`, `BD`): keine Antwort nach ENQ. Das Ergebnis wird mit `AP` gelesen.

Antwortrahmen haben dieselbe Form wie Befehlsrahmen, die Nutzlast ist die Antwort. Beispiel `AP`: `02 30 30 00 06 S F 0 0 1 4 03 BCC`, also Nutzlast `"SF0014"`.

## 4. Zeitverhalten

- Maximal 15 ms zwischen Befehlsbytes (Liste 1), 50 ms (Liste 2).
- Zwischen zwei Statusabfragen mindestens 200 ms.
- Kein neuer Befehl, bevor der vorherige abgeschlossen ist. Der Abschluss ist erst erreicht, wenn der Status stabil ist.
- Lesen der Antwort: mit exakter Länge lesen. Eine `AP`-Antwort hat 13 Bytes. Mit einem festen Lesepuffer (z. B. 64 Byte) wartet der Port bis zum Timeout, im Test 1,58 s pro Abfrage.

## 5. Befehle

| Zweck                          | Befehl             | Bewegung | Verhalten                                                                                  |
|--------------------------------|--------------------|----------|--------------------------------------------------------------------------------------------|
| Status lang                    | `AP` (0x41 0x50)   | nein     | Antwort `SF` + 4 Hex-Ziffern (Bitmaske, siehe Abschnitt 6)                                  |
| Status kurz                    | `RF` (0x52 0x46)   | nein     | Antwort `SF` + 3 Hex-Ziffern, gleiche Bits                                                  |
| Firmware                       | `GV` (0x47 0x56)   | nein     | Antwort `PGV<Version>`, z. B. `PGVTTCE_K720_V104`                                           |
| Karte suchen (S50)             | `0x3B 0x30`        | nein     | Erfolg `P;0` + Nutzlast (`04 00`), Fehler `N;...`                                           |
| UID lesen (S50)                | `0x3B 0x31`        | nein     | Erfolg `P;1` + 4 UID-Bytes, Fehler `N;...`                                                  |
| Karte von Stapel nach User     | `DC` (0x44 0x43)   | ja       | Sensor Stapel -> Sensor User (`0x0001`)                                                     |
| Karte nach Leseposition        | `FC7` (0x46 0x43 0x37) | ja   | Ergebnis Sensor Lesen und Sensor User (`0x0003`). Abgelehnt aus L+U (`0x4013`).             |
| Karte nach Lesen (von Stapel)  | `FC6` (0x46 0x43 0x36) | ja   | Nur aus Sensor Stapel allein (`0x0014` -> `0x0006`). Abgelehnt aus U, L, L+U, L+S.          |
| Karte Lesen -> User            | `FC4` (0x46 0x43 0x34) | ja   | Aus L, L+U, S, L+S, U. Ergebnis `0x0001`.                                                    |
| Auswurf (NICHT Regelbetrieb)   | `FC0` (0x46 0x43 0x30) | ja   | Wirft die Karte aus dem Gerät aus. Nicht lesbar, nicht registriert. Siehe Abschnitt 8.      |
| Ablage (Entsorgung)            | `CP` (0x43 0x50)   | ja       | Nur aus Sensor Lesen oder Sensor User. Abgelehnt aus S allein (`0x4014`).                  |
| Reset                          | `RS` (0x52 0x53)   | nein     | Keine Wirkung auf Sensorbits, Quittungston am Gerät.                                       |
| Buzzer ein / aus               | `BE` / `BD`        | nein     | Keine Antwort-Nutzlast. Im Test kein hörbarer Ton beobachtet, Wirkung offen.              |

Nicht verwenden: `CS0`..`CS5` (Baudrate, bricht die Verbindung), `DB` (vom Gerät mit `N` `DB` `0x00` beantwortet, nicht unterstützt).

Antworten mit Fehlerbit: Ein Befehl, der nicht ausgeführt werden kann, erzeugt im `AP`-Status das Bit `0x4000` (Befehl abgelehnt). Das ist transient. Der Status muss danach erneut gelesen werden.

## 6. Statusbits (`AP`, 16-Bit)

| Bit      | Bedeutung                                     | Verhalten im Treiber                       |
|----------|-----------------------------------------------|--------------------------------------------|
| `0x0800` | Karte wird ausgegeben                         | informativ, Ablauf läuft                   |
| `0x0400` | Karte wird eingezogen (Ablage)                | informativ                                 |
| `0x0200` | Fehler bei Ausgabe                            | blockierend, typisierter Fehler            |
| `0x0100` | Fehler bei Ablage                             | blockierend, typisierter Fehler            |
| `0x0080` | No captured card (Name laut Handbuch)         | nicht ausgewertet                          |
| `0x0040` | Karte überlappt                               | blockierend, typisierter Fehler            |
| `0x0020` | Karte klemmt                                  | blockierend, typisierter Fehler            |
| `0x0010` | Vorrat unter Schwelle (Warnung)               | Warnung in der UI, nicht blockierend       |
| `0x0008` | Vorrat leer (Zustand, kein Sensor)            | harter Stopp, keine Ausgabe                |
| `0x1000` | Vorbereitung (transient)                      | kein Fehler, nicht stabil auswerten        |
| `0x4000` | Befehl abgelehnt (transient)                  | Befehl nicht wiederholen ohne neue Prüfung |
| `0x0004` | Sensor Stapel belegt                          | Karte am Stapelausgang                     |
| `0x0002` | Sensor Lesen belegt                           | Karte an Leseposition                      |
| `0x0001` | Sensor User belegt                            | Karte am Ausgang für den Nutzer            |

Die Sensornamen sind fest: Sensor User (`0x0001`), Sensor Lesen (`0x0002`), Sensor Stapel (`0x0004`). Die Vorratsschwelle wird am Gerät eingestellt, 5 bis 72 Karten (zweiter Extended Rack). Es gibt keine feste Kartenzahl im Code.

Zustand "Karte im Schacht" ist nicht sicher aus dem Status ablesbar. Die Anzahl ist nur Nutzerangabe.

## 7. Zustände und Lesbarkeit

Bezeichnungen (Zustand = Sensorbelegung):

- U = nur Sensor User (`0x0001`)
- L = nur Sensor Lesen (`0x0002`)
- S = nur Sensor Stapel (`0x0004`)
- L+U = Sensor Lesen und Sensor User (`0x0003`)
- L+S = Sensor Lesen und Sensor Stapel (`0x0006`)

Lesen per `0x3B 0x30` / `0x3B 0x31` funktioniert:
- aus **L** (gemessen, UID `8388B21A`),
- aus **L+U** (gemessen).

Nicht lesbar: L+S (Rückfallposition nach fehlerhaftem `FC6`).

Nicht gemessen: U allein, S allein, U+S (`0x0005`).

Befehlsmatrix (gemessen, Zustand nach Befehl):

| Befehl | U | L | S | L+U | L+S |
|---|---|---|---|---|---|
| DC  | Justage, bleibt U | -> U | -> U | -> U | -> U |
| FC7 | -> L+U | -> L+U | -> L+U | abgelehnt (`0x4013`) | -> L+U |
| FC6 | abgelehnt | abgelehnt | -> L+S | abgelehnt | abgelehnt |
| FC4 | Justage, bleibt U | -> U | -> U | -> U | -> U |
| FC0 | Auswurf | Auswurf | Auswurf | Auswurf | Auswurf |
| CP  | -> S (Ablage) | -> S (Ablage) | abgelehnt | -> S | -> S |
| RS  | keine Bewegung | keine Bewegung | keine Bewegung | keine Bewegung | keine Bewegung |

Hinweise zur Matrix:
- "Justage": kurze Vor- und Rückbewegung, Endzustand unverändert.
- DC aus U und FC8 wurden gemessen; FC8 hatte keine Wirkung per Status (Einzelmessungen mit und ohne Nutzerbeobachtung).
- Zustand U+S (`0x0005`) ist nie beobachtet worden.

## 8. Auswurf (FC0): gefährlich, nicht im Regelbetrieb

- Eine mit `FC0` ausgeworfene Karte wird von der nächsten Ausgabe **nicht** weggeschoben. Sie bleibt im Schacht und verstopft ihn.
- Folge: Ein Schachtstau ist nicht mechanisch sicher behebbar, ohne den roten Knopf am Gerät zu verwenden.
- Regel: `FC0` im Dispense-Flow nicht verwenden. Nur mit ausdrücklicher Freigabe und mit anschließender Kontrolle des Schachts.

## 9. Ablauf Ausgabe (Empfehlung)

1. `AP` lesen. Blockierende Bits (`0x0200`, `0x0100`, `0x0040`, `0x0020`, `0x0008`) prüfen, bei Treffer Fehler werfen, kein Befehl.
2. `DC` senden (ACK, ENQ).
3. `AP` im Abstand von mindestens 200 ms lesen, bis stabil. Ergebnis Sensor User (`0x0001`) ist das Ziel.
4. Karte vom Nutzer entnehmen lassen (Sensor User wieder frei).
5. Für das Lesen die Karte auf Leseposition bringen: `FC7` aus einem Zustand mit Karte am Ausgang (`0x0001`). Ergebnis `0x0003`.
6. `0x3B 0x30` (Suche), dann `0x3B 0x31` (UID). Nur bei `P;0` bzw. `P;1` und vollständigen 4 UID-Bytes gilt die Karte als gelesen.
7. Karte persistieren, erst nach erfolgreichem Lesen.

Dieser Ablauf ist die Empfehlung. Schritt 5 (`FC7` aus Ausgang) ist gemessen (Zustand U -> L+U), Schritt 4 (Entnahme) ist eine Nutzeraktion.

## 10. Bekannte Einschränkungen und offene Punkte

- Die Antwort auf `0x3B 0x31` ist `P;1` gefolgt von 4 UID-Bytes. CLAUDE.md nennt `P;3B31`, das wurde am Gerät nicht bestätigt.
- Stapel-Mechanik: Beim Einschub einer Karte von vorne während eine Karte an Sensor Stapel steht, kann die Stapelkarte zurück in den Stapel geschoben werden und sich dort festklemmen. Das ist der größte anzunehmende Fehlerfall. Der Status zeigt das nicht zuverlässig.
- Ein `CP`-Befehl wurde in einem Lauf quittiert, die Karte blieb aber in Sensor Lesen und Sensor User. Ursache nicht geklärt. Ob es eine andere Kartenart ist, ist offen.
- `BE` hat im Test keinen hörbaren Ton erzeugt. Die Wirkung von `BD`/`BE` ist offen.
- Die Ablagebox-Füllung wird nicht gezählt. Der K720 zählt keine Karten; das Bit `0x0080` ist für den K720 nicht relevant (der Zählsensor gehört zum K750).
- `0x1000` (Vorbereitung) tritt nach Auswurf und während des Nachladens des Stapels auf. Ob es auch bei normaler Vorbereitung erscheint, ist nicht geprüft.
- Die Sensornamen sind Projektnamen. Im Handbuch heißen die Sensoren anders (Sensor 1 Vorab-Einzug, Sensor 2 Leseposition, Sensor 3 Kartenmund). Für die Implementierung gelten die Projektnamen.

### 10.1 Beobachteter Stau U+S mit Ueberlappung (Sitzung, Messung am Geraet)

Befund (gemessen, nicht reproduzierbar auf Befehl):

- `FC4` aus L+U (`0x0003`) ergab stabil `0x0015` (U+S, Vorrat-Warnung aktiv). Das ist der bisher unbeobachtete Zustand U+S, jetzt gemessen.
- Nachfolgend `FC7` aus U+S: `CardOverlapError`, Status `0x0256` (Ausgabefehler `0x0200`, Ueberlappung `0x0040`, L+S). Der Befehl wurde vom Geraet nicht ausgefuehrt, die Bits blockieren.
- `CP` aus diesem Zustand: ACK, danach `0x4256` (Befehl abgelehnt), dann wieder `0x0256`. Keine Bewegung.
- `FC0` aus diesem Zustand: ACK, danach `0x1056` (Vorbereitung, Ueberlappung bleibt). Ausgabefehler-Bit weg. Ob dabei eine Karte ausgeworfen wurde, ist nicht gemessen.
- Danach stabil `0x0054` (Ueberlappung, Vorrat-Warnung, Stapel belegt). Keine Leseposition, kein Ausgang.
- `RS` aus `0x0054`: ACK, danach stabil `0x0014`. Die Ueberlappung ist geloest. Damit weicht die Beobachtung von der Tabelle in Abschnitt 5 ab, die fuer `RS` keine Wirkung auf die Sensorbits angibt. Einmal beobachtet, nicht wiederholt.

Einschraenkung (Nutzerbefund, Sichtpruefung am Geraet):

- Die klemmende Karte steckt am Ausgang Sensor User und blockiert die Ausgabe neuer Karten. Der Status zeigt das nicht: Nach `RS` ist der Ausgang frei, obwohl die Karte dort steckt.
- Die Karte ist ausserhalb des Sensorbereichs fuer den K720 nicht erkennbar. Der Treiber kann den Stau nicht selbst beheben.
- Konsequenz: `RS` ist kein Ersatz fuer die Entnahme. Die Ausgabe bleibt blockiert, bis die Karte entfernt wurde.

Zulaessige Behandlung (Freigabe durch Admin erforderlich, nicht durch den Treiber entscheidbar):

1. Stau erkannt (U+S oder Ueberlappung): Geraet sperren, keine weitere Ausgabe, Stoerung anzeigen.
2. Admin entfernt die Karte aus dem Ausgang, oder bei klemmender Karte drueckt er die rote Taste am Geraet.
3. Admin bestaetigt die Entnahme in der Software. Erst danach darf `AP` wieder als regulaer gelten und die Ausgabe starten.

`FC0` wird dafuer nicht verwendet (Abschnitt 8).

Weitere Messungen in derselben Sitzung:

- `FC4` aus L+U (`0x0013`) ergab zum zweiten Mal U+S (`0x0015`), stabil. U+S ist damit reproduzierbar.
- `FC8` aus U+S (`0x0015`): ACK, keine Aenderung des Status. Die Sichtpruefung der vorderen Karte stand aus.
- `FC4` aus `0x0017` (U+L+S, mit Ueberlappung): erzeugte `0x0257` (Ausgabefehler, Ueberlappung), stabil.
- `FC0` aus `0x0257`: ACK, Status unveraendert `0x0257`.
- `RS` aus `0x0257`: ACK, danach `0x0017`, ohne blockierende Bits. Die Ueberlappung und der Ausgabefehler wurden durch `RS` zurueckgesetzt.
- `FC0` aus `0x0017`: ACK, danach wieder `0x0257`. `FC0` loest den Fehler nicht.
- Nach dem Nutzer-Eingriff (roter Knopf, Entnahme durch Person am Geraet) stabil `0x0016`, danach `0x0014`. Der Stau war damit behoben.
- `RS` aus `0x0014` (nach Entnahme, Stapel belegt): ACK, danach nach ca. 3 s `0x0017` (Ausgang, Leseposition, Stapel belegt). `RS` veraendert die Sensorbelegung also auch ohne Ueberlappung. Das widerspricht der Tabelle in Abschnitt 5 (keine Bewegung) und ist in der Sitzung zweimal beobachtet.

Zusammenfassung fuer die Behandlung: `RS` ist kein sicheres Mittel gegen Staus, es kann Sensorzustaende verschieben. `FC0` ist ausgeschlossen. Ein Stau mit Ueberlappung braucht eine Person am Geraet und eine Bestaetigung, dass der Schacht frei ist.

Ablauf FC7 aus S -> Lesen -> FC4 aus L+U (gemessen):

- `FC7` aus S (`0x0014`): ergab L+U (`0x0013`).
- UID-Lesen aus L+U: erfolgreich (8 Hex-Zeichen, Wert nicht protokolliert).
- `FC4` aus L+U: ergab U (`0x0011`), stabil. Diesmal kein U+S.
- Danach nach ca. 1,2 s `0x1010` (Vorbereitung, Vorrat-Warnung), dann stabil `0x0014` (nur Stapel).
- Nutzer-Befund: Die Karte am Ausgang wurde entnommen. Mechanisch kam danach automatisch eine Karte aus dem Vorrat in den Stapel (Sensor Stapel). Das erklaert `0x1010` und `0x0014` ohne weiteren Befehl.

Damit ist der Ablauf Entnahme -> automatische Nachladung des Stapels in der Messung belegt.

Annahme-Ablauf (Nutzer schiebt Karte von vorne ein, ohne Befehl):

- Start `0x0014` (S), stabil.
- Einzug durch Nutzer: nach ca. 4,7 s `0x0013` (L+U), kein Befehl gesendet.
- UID aus L+U gelesen (8 Hex-Zeichen, Wert nicht protokolliert).

Ausgabe und Recycling derselben Sitzung:

- `FC4` aus L+U: Karte nach vorne gebracht, vom Nutzer entnommen. Der Treiber meldete `HardwareTimeoutError` ("card did not reach user exit"), weil der Nutzer die Karte entnahm, bevor der Status als stabiles U gelesen wurde. Der Geraetezustand war erwartungsgemaess, das Problem liegt in der Wartebedingung des Treibers (siehe Folgerung unten).
- Neue Karte eingeschoben, Status stabil `0x0013` (L+U), UID aus L+U gelesen (8 Hex-Zeichen).
- `CP` aus L+U: ACK, danach stabil `0x0014` (nur S), keine blockierenden Bits. Karte aus Leseposition und Ausgang verschwunden. Ablage in die Recyclingbox: Nutzer-Bestaetigung ausstehend.

Folgerung fuer den Treiber:

- `_wait_for_status` akzeptiert eine Bewegung erst, wenn der Zielzustand zweimal hintereinander gelesen wurde. Entnimmt der Nutzer die Karte schneller, laeuft das in einen Timeout, obwohl das Geraet korrekt gearbeitet hat. Der Service muss diesen Fall als "Karte entnommen, Zielzustand nicht bestaetigt" behandeln, nicht als Geraetefehler. Offen, nicht geaendert.
