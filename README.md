# Kiosk Card Dispenser

Lokales MVP/Proof-of-Concept fuer Ausgabe und Verwaltung von K720-Karten unter Ubuntu 24.04 LTS. Das Kiosk nutzt PySide6/QML, SQLite und einen seriellen K720-Kartenautomaten. Bargeld wird ausserhalb der Software vom Gatekeeper entgegengenommen und am Terminal bestaetigt.

## Start mit AI-Harness
Repository in einem AI-Coding-Harness oeffnen und die Tasks der Reihe nach von `tasks/00-project-setup.md` bis `tasks/07-integration-and-kiosk.md` ausfuehren. Vor dem Hardware-Task **zuerst `docs/k720_protocol.md` einfuegen/mit der echten, Python-basierten Hersteller-Befehlsbeschreibung ausfuellen**. Keine K720-Befehle erfinden; bis dahin nur Interfaces und Fakes erstellen.

Die fachlichen Anforderungen stehen in `docs/domain.md`; Setup-Schritte in `docs/setup-ubuntu.md`. Kein produktiver Hardwarebetrieb mit Fakes.
