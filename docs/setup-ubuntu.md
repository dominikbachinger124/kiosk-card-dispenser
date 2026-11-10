# Einrichtung unter Ubuntu 24.04 LTS

## System und Python
Ubuntu 24.04 LTS installieren und Updates einspielen. Projektpflege erfolgt mit `uv` (`pyproject.toml` + `uv.lock`). Entwicklungsziel ist Python 3.12 (`.python-version`); Python >=3.11 ist ebenfalls zulaessig. Fehlende Interpreter bereitstellen mit `uv python install 3.11 3.12`. Keine System-Python-Installation ueberschreiben und kein `pip`/`venv` fuer Projektabhaengigkeiten verwenden.

```bash
sudo apt update
sudo apt install -y build-essential git curl

# uv installieren (einmalig, Benutzerinstallation)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Im Projektverzeichnis: Interpreter und Abhaengigkeiten aus uv.lock
uv python install 3.12
uv sync
```

`uv sync` legt die `.venv` im Projekt an und installiert Laufzeit- sowie Entwicklungsabhaengigkeiten exakt gemaess `uv.lock`. Dev-Werkzeuge (pytest, ruff, mypy) sind Teil der Dependency-Gruppe `dev` in `pyproject.toml`. Kiosk-Start und Tests erfolgen mit `uv run`, nicht durch manuelles Aktivieren der venv.

Abhaengigkeiten aendern nur mit `uv add <paket>` (Laufzeit) bzw. `uv add --dev <paket>` (Entwicklung); das aktualisiert `uv.lock`, das zusammen mit `pyproject.toml` committet wird.

## Serieller K720-Anschluss
Adapter RS-232 ueber USB-to-Serial anschliessen und Device ermitteln:

```bash
ls -l /dev/serial/by-id/
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
sudo usermod -aG dialout "$USER"
```
Ab- und wieder anmelden (oder neu starten), damit Gruppenmitgliedschaft gilt; pruefen mit `id`. In lokaler Config bevorzugt stabilen Pfad `/dev/serial/by-id/...` setzen. udev-Links/Geraeteberechtigungen pruefen. Niemals Baudrate/Frames/Befehle raten: erst echte Protokollbeschreibung in `docs/k720_protocol.md` eintragen und Hardwareabnahme durchfuehren. Kein produktiver Start, solange Protokollplatzhalter besteht.

## Touchscreen, Vollbild und Anzeige
USB-Touchscreen anschliessen und Eingabegeraet unter Desktop-Umgebung pruefen. Qt waehlt Wayland bzw. X11-Plattform automatisch; Sitzungsart kontrollieren:

```bash
echo $XDG_SESSION_TYPE
```
App im Vollbild starten; Aufloesung, Touch-Kalibrierung, Skalierung und Orientierung am Zielgeraet testen. Screensaver, automatische Bildschirmsperre und Display-Blanking fuer dedizierte Kiosk-Sitzung deaktivieren bzw. so konfigurieren, dass Kiosk-Screensaver/Hardwarepolling weiterlaufen.

## Konfiguration und Benutzer
Dedizierten, nicht privilegierten Kiosk-User anlegen. Nur benoetigte Rechte vergeben, `dialout` fuer serielle Hardware. `config.toml` mit Betriebsmodus `real`, stabilen Device-Pfaden und Werten aus Beispiel ausfuellen; Salt und Admin-PIN-Hash sicher lokal bereitstellen, `config.local.toml` nie committen. Vor Betrieb echte Hardware, Ausgabe, Rueckgabe, Recycling, Portverlust und Notfallablauf testen.

## Ausgabe-Watch und Log
Nach einer Ausgabe wartet der Kiosk bis zu 45 Sekunden, ob der Kunde die Karte entnimmt (`wait_s`, Standard 45). Die Prüfung läuft jede Sekunde (`check_interval_s`). Tastendruck während dieser Wartezeit bricht den Watch ab; die Karte wird dann über die UID-Prüfung eingezogen und verbucht. Details: `docs/k720_protocol.md`, Abschnitt 9.

Das Log schreibt standardmäßig nach `~/.local/state/kiosk/logs/kiosk.log` (JSON-Zeilen, Verzeichnis 0700, Datei 0600). Für einen Test mit eigenem Verzeichnis: `uv run python -m kiosk --log-dir <pfad>`.

## systemd User Service (Vorlage)
Datei `~/.config/systemd/user/kiosk-card-dispenser.service` lokal anlegen und Pfade/User anpassen:

```ini
[Unit]
Description=Kiosk Card Dispenser
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=%h/kiosk-card-dispenser
ExecStart=%h/.local/bin/uv run --project %h/kiosk-card-dispenser python -m kiosk
Restart=on-failure
RestartSec=5
Environment=QT_AUTO_SCREEN_SCALE_FACTOR=1

[Install]
WantedBy=default.target
```

Aktivieren in grafischer Benutzersitzung:

```bash
systemctl --user daemon-reload
systemctl --user enable --now kiosk-card-dispenser.service
systemctl --user status kiosk-card-dispenser.service
```
Ein User-Service braucht aktive grafische Session und korrekte Qt-Plattformumgebung. Autologin fuer dedizierten Benutzer nur nach Risikoabwaegung und ohne automatische Admin-Anmeldung konfigurieren. Logs via `journalctl --user -u kiosk-card-dispenser.service` pruefen.
