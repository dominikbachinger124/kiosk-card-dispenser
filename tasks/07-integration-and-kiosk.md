# Task 07 - Integration und Kiosk-Betrieb

## Ziel
Fuehre Schichten zusammen, liefere reproduzierbaren Kioskstart und E2E-/manuelle Abnahmeunterlagen fuer Ubuntu 24.04 und echte Hardware.

## Vorbedingungen
Tasks 00-06 abgeschlossen, Einzeltests gruen. Lies `docs/setup-ubuntu.md`, `docs/security-notes.md`, `docs/architecture.md`. Echte Hardwareabnahme nur nach vollstaendig verifiziertem `docs/k720_protocol.md`.

## Konkrete Schritte
1. App-Entry-Point und Konfigurationsvalidierung bereitstellen. Betriebsmodus ausschliesslich real; kein Fake-Fallback, wenn Hardware fehlt.
2. Vollstaendigen Flow durch Services, SQLite, Worker, Qt/QML und Admin integrieren. Shutdown beendet Worker und schliesst DB kontrolliert.
3. E2E-Tests mit Fake-Interfaces ausschliesslich in Testprozess; pruefe Neu-/Weitere-Karte, Aufladung, Balance, Recycling, Demo-Zahlung, Auto-Erkennung und Admin-Auszahlung.
4. Aktualisiere README mit Installation, Start im AI-Harness, Protokollvorbedingung, Testlauf und Betriebswarnungen. Verweise auf alle sechs Dokumente in `docs/`.
5. Stelle Autostart/systemd-User-Service-Vorlage und Kioskdiagnose bereit; folge `docs/setup-ubuntu.md` fuer `dialout`, stabile Device-ID und Wayland/X11.
6. Erstelle manuelle Abnahme-Checkliste fuer Touch/Vollbild, echte Ausgabe, Lesen, Rueckgabe, Recycling, Portverlust, klemmende Karte, Bargeldbestaetigung, DB/WAL/Backup, Admin-PIN, Neustart und Recovery. Nur nach echtem Herstellerprotokoll ausfuehren.
7. Pruefe Secrets, Logs, Dateiberechtigungen, Migrationen, Fehlertexte, Konfigurationswerte und kein Netzwerkverhalten.

## Akzeptanzkriterien
Alle Tests gruen; Installation und Start dokumentiert; echte Hardware wird ohne valide Config/Device nicht als erfolgreich gemeldet. Fakes bleiben Test-only. Manuelle Abnahme benennt Voraussetzungen und bekannte MVP-Grenzen. Keine nicht dokumentierten Protokollbefehle.

## Tests
`python -m pytest -q` vollstaendig und E2E mit Fakes. Statisches Linting optional (Ruff/mypy). Manuelle Abnahme unter Ubuntu 24.04 in Wayland- und X11-Sitzung, falls vorhanden. Hardwaretests nur nach Protokollverifikation; Ergebnisse und nicht gepruefte Punkte explizit dokumentieren.
