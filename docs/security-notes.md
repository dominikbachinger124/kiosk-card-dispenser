# Sicherheits- und Datenschutznotizen

## MVP-Grenzen
Dies ist ein lokales MVP/Proof-of-Concept, kein zertifiziertes Zutritts- oder Zahlungssystem. Ein unsignierter Ausweisleser ist manipulierbar/kopierbar; spaeter ist fuer hoehere Schutzanforderungen ein kryptografischer High-Security-Reader mit Challenge-Response und sicherer Schluesselverwaltung erforderlich. Im MVP-Demo-Modus kann der 24-Stunden-Cooldown umgangen werden (`cooldown_enforced=false`); Restzeit wird angezeigt, Nutzung aber nicht blockiert. Bargeldannahme wird nicht technisch verifiziert, sondern vom Gatekeeper bestaetigt. DummyPayment ist keine echte Zahlungsabwicklung.

## Datensparsamkeit und Hashing
Nur Ausweiskennung (Kartennummer/UID) lesen. Vor Persistenz SHA-256 mit geheimem, zufaelligem Salt aus lokaler Config anwenden; niemals Rohkennung, sonstige Ausweisdaten oder Salt loggen. Salt darf nicht ins Repository. Hashes koennen bei bekanntem kleinem Kennungsraum angreifbar bleiben; Zugriff auf DB-Datei und Backup einschränken. Nur notwendige Zeit-/Vorgangsmetadaten speichern und Aufbewahrung organisatorisch festlegen.

## Admin-PIN und Admin-Karten
PIN ausschliesslich als adaptiver Hash speichern, vorzugsweise `hashlib.scrypt` mit individuellem Salt, ausreichenden Parametern und Vergleich in konstanter Zeit; Klartext-PIN weder im Repo noch in Logs/DB halten. Fehlerzahl/Verzoegerung begrenzen, Admin-Ereignisse auditieren. Admin-UIDs lokal konfigurieren (ein bis zwei); das allein ist kein kryptografischer Schutz.

## Ledger und Audit
Ledger append-only: keine Buchungen aendern oder loeschen; Korrektur durch Gegenbuchung und dokumentierten Grund. Admin-Audit fuer PIN-Erfolg/-Fehler, Kontosuche im noetigen Umfang, Auszahlung, Kontoschliessung und Kartenstornierung. Keine Geheimnisse oder Rohkennungen im Audit. DB-/Log-Berechtigungen minimieren, Backups schuetzen und Restore testen.

## Netzwerk und Betrieb
Kein Netzwerkzugriff fuer MVP-Funktionen, keine Cloud-Synchronisierung und keine Online-Zahlung. Host regelmaessig aktualisieren, Kiosk-User mit minimalen Rechten, seriellen Zugriff gezielt ueber Gruppe `dialout` und stabile Device-Pfade. Secrets aus Umgebung/lokaler ignorierter Config bereitstellen. SQLite-Datei, WAL/SHM, Logs und Sicherungen vor anderen lokalen Benutzern schuetzen. Keine Fake-Hardware im Betriebsmodus; Fehler muessen sichtbar und fail-closed behandelt werden.

## Restrisiken
Physische Manipulation von Terminal, USB, Karten, unbeaufsichtigtem Bargeld und lokaler DB ist nicht durch die MVP-Software geloest. Kein manipulationssicherer Audit-Speicher. Betreiber muessen Kassenabgleich, Admin-Zugriff und Hardwareabnahme vorsehen. Produktive Nutzung erfordert Bedrohungsanalyse, Datenschutzpruefung und geeignete Hardware-/Betriebsmassnahmen.
