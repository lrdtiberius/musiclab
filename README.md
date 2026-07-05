# MusicLab v1.3.7

Musikbibliothek scannen, LUFS/True-Peak/LRA analysieren und Alben oder Titel normalisieren.

## Projektstruktur

```text
MusicLab/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       └── main.py
├── frontend/
│   ├── Dockerfile
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   └── assets/
├── data/
│   ├── backups/
│   └── logs/
├── docker-compose.yml
├── README.md
└── LICENSE
```

## Synology-Installation

1. Den kompletten Ordner nach `/volume1/docker/musiclab` kopieren.
2. Im Container Manager ein neues Projekt aus diesem Ordner erstellen.
3. Projekt starten.
4. Oberfläche öffnen: `http://<NAS-IP>:8092`
5. Backend API: `http://<NAS-IP>:8091/api/status`

## Hinweise

- Der Ordner `data/` ist absichtlich enthalten und wird für Datenbank, Logs und Backups genutzt.
- Frontend-Dateien liegen jetzt sauber getrennt in `frontend/index.html`, `frontend/app.js` und `frontend/styles.css`.
- macOS-Metadatenordner wie `__MACOSX` und `._*` sind nicht enthalten.

Idea by Lrd.Tiberius.


## Version 1.2.0

- Layout-Refactoring: Albumliste und Titelliste ergonomischer nebeneinander.
- Album-Aktionen kompakter in der Albumsektion.
- Titelbereich deutlich breiter.
- Log/Historie größer und gleichmäßiger.
- Ein-Bildschirm-Layout bleibt erhalten.
- Footer mit Idea by Lrd.Tiberius bleibt sichtbar.


## v1.2.3
- Musikpfad kann in den Einstellungen als Container-Pfad angepasst werden.
- Pfadprüfung für den Musikordner ergänzt.


## v1.2.3
- Albumaktionen im Albumbereich als Dropdown statt breiter Buttonleiste.
- Albumliste bleibt sichtbar und wird nicht mehr von Aktionsbuttons überlagert.
- Version auf v1.2.3 aktualisiert.


## v1.3.7

- Linke Navigation erweitert: Interpreten / Alben / Neu.
- „Neu“ zeigt Alben mit noch offenen, nicht analysierten Titeln als Arbeitsliste.
- Einstellungen erweitert: Überwachung aus / nur melden / automatisch scannen / scannen + analysieren.
- Hintergrund-Watcher prüft den Musikordner regelmäßig auf Änderungen.
- Version auf v1.3.7 aktualisiert.


## v1.3.7

- Hauptnavigation mit Audio / Tags / Einstellungen oben rechts.
- Einstellungen sind jetzt eine eigene Ansicht statt Popup.
- Neue Tags-Ansicht zum Bearbeiten von Album- und Titel-Tags.
- Version auf v1.3.7 aktualisiert.


## v1.3.7
- Albumsuche funktioniert wieder global, auch wenn vorher ein Interpret ausgewählt wurde.
- Suchfeld hat ein X zum schnellen Leeren.
- Tags-Seite berechnet „Tracks pro Album“ bei Samplern/mehreren Interpreten über das komplette Album statt nur über den zuletzt gewählten Interpreten.


## v1.3.7

- Genre-Feld als Combo-Feld mit vorhandenen Genres aus der Bibliothek.
- Disc-Anzahl ergänzt: Disc pro Titel + Discs pro Album.
- Track-/Disc-Speicherung erzeugt automatisch Werte wie 1/10 und 1/2.
- Datenbank-Schema auf 15 aktualisiert.


## v1.3.7
- Scan-Fehler behoben: fehlender `genre`-Parameter beim Speichern von Tracks.
- Versionsnummern in Backend, Frontend und README vereinheitlicht.
- Cache-/Pycache-Dateien aus dem ZIP entfernt.
