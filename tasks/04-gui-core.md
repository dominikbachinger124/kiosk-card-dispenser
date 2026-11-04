# Task 04 - GUI-Grundgeruest

## Ziel
Implementiere den barrierearmen Vollbild-Kioskrahmen mit Screensaver, Navigation und Orbit-Menue gemaess `docs/ui-spec.md`.

## Vorbedingungen
Tasks 00-03 abgeschlossen und Tests gruen; Service-API bekannt. Lies `docs/ui-spec.md` und `docs/architecture.md`.

## Konkrete Schritte
1. Erzeuge PySide6/QML-App im Vollbild mit Qt-Plattformauswahl automatisch unter Wayland/X11.
2. Erstelle ViewModels/Controller, die Services aufrufen; keine Buchungslogik in QML. UI bleibt reaktionsfaehig waehrend Hardware/DB-Operationen.
3. Implementiere Screensaver und Inaktivitaets-Timeout; Hardwarepolling bleibt aktiv.
4. Implementiere genau sieben Orbit-Eintraege, Touch-gross, lesbar, kontrastreich, mit dezenter Kreis-/Schwebe-Animation und klarer Navigation.
5. Ergaenze zentrale Deutsch-/Englisch-Texte und Deutsch als Default. Bewegung abschwaechbar; UI-Texte nicht verstreut duplizieren.
6. Ergaenze globale Busy-, Erfolg-, Fehler- und Abbruchzustaende sowie Wecken durch `card_inserted`.

## Akzeptanzkriterien
Startet ohne K720-Protokollannahmen im Entwicklungs-/Testmodus; Vollbild, sieben Eintraege und Screensaver sind vorhanden. Keine Kontodaten/Regeln in QML. GUI-Thread bleibt frei von blockierender IO; Accessibility-Grundregeln eingehalten.

## Tests
pytest fuer ViewModel-Zustandsuebergaenge und Lokalisierungsfaelle; QML-/GUI-Smoke-Test mit offscreen Qt, soweit Umgebung erlaubt. Manuelle Pruefung Touchziele, Kontrast, Aufloesung, Screensaver und Wayland/X11.
