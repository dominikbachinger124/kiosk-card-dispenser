# Einrichtung unter Ubuntu 24.04 LTS

## System und Python
Ubuntu 24.04 LTS installieren und Updates einspielen. Ziel ist Python 3.11; wenn das System nur Python 3.12 anbietet, ist Python >=3.11 einschliesslich 3.12 zulaessig. Python 3.11 bei Bedarf kontrolliert via `uv` oder einem gepflegten Paketweg (z.B. deadsnakes) bereitstellen; keine System-Python-Installation ueberschreiben.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip build-essential git
# In Projektverzeichnis:
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install pyside6 pyserial pytest
```

Optional fuer Entwicklung: `ruff` und `mypy` installieren. Projektabhaengigkeiten spaeter ueber pyproject/Lock-Prozess reproduzierbar verwalten.

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

## systemd User Service (Vorlage)
Datei `~/.config/systemd/user/kiosk-card-dispenser.service` lokal anlegen und Pfade/User anpassen:

```ini
[Unit]
Description=Kiosk Card Dispenser
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=%h/kiosk-card-dispenser
ExecStart=%h/kiosk-card-dispenser/.venv/bin/python -m kiosk
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
