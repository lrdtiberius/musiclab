# MusicLab v1.8.24

## v1.8.24

- Tags-Scraper schreibt keine Titel, Tracknummern, Discnummern, Interpret- oder Album-Tags mehr.
- Scraper-Aktionen getrennt: Nur Jahr, Nur Cover, Jahr + Cover.
- Bestätigungsdialog erklärt ausdrücklich, dass Trackdaten nicht überschrieben werden.


## Änderungen

- Live-Log-Zeit auf `Europe/Berlin` umgestellt.
  - `TZ=Europe/Berlin` und `LOG_TZ=Europe/Berlin` sind in `docker-compose.yml` gesetzt.
  - Neue Logeinträge verwenden dadurch die lokale Uhrzeit statt UTC.
- Kachel-Überschriften auf Duplikate- und Protokollseite stabilisiert.
  - Hinweise/Buttons rutschen nicht mehr in die falsche Zeile.
  - Die einzelnen Kacheln behalten wieder saubere Kopfbereiche.
- Basis bleibt v1.8.13/v1.8.14 mit:
  - Duplikatseite ohne linke Suche/Liste
  - keine Pfad-Öffnen-/Pfad-Kopieren-Buttons
  - Tag-Sortierung bevorzugt saubere Umlaut-Schreibweise wie `Die Ärzte` statt `Die Arzte`

## Nach dem Update

```bash
docker compose down
docker compose up -d --build
```

Danach im Browser hart neu laden.

Hinweis: Bereits vorhandene alte Logzeilen behalten ihre alte Uhrzeit. Die Korrektur gilt für neue Logeinträge nach dem Neustart.


## v1.8.24

- Tags-Seite erweitert: neuer Suchtyp „Fehlende/fehlerhafte Tags“.
- Betroffene Albumordner werden links gesammelt angezeigt und öffnen direkt den vorhandenen Tag-Editor.
- Erkannt werden u. a. fehlender Interpret, Album, Titel, Jahr, Genre, Tracknummer sowie uneinheitliche Tags innerhalb eines Albumordners.
- Ordner-/Tag-Schreibweisen werden als Hinweis markiert, z. B. wenn Ordnername und Tag-Schreibweise abweichen.


## v1.8.24

- Neuer Button **Alles normalisieren** in der Kopfzeile.
- Normalisiert alle vollständig analysierten Alben auf die eingestellten Zielwerte.
- Nicht vollständig analysierte Alben und Referenzalben werden übersprungen und vorher im Bestätigungsdialog angezeigt.


## v1.8.24
- Tag-Scraper zeigt pro Treffer eine Gegenüberstellung deiner sichtbaren Tracks mit den MusicBrainz-Tracks.
- Die Gegenüberstellung dient nur zum schnellen Abgleich; Titel, Tracknummern, Discnummern, Interpret und Album werden weiterhin nicht automatisch überschrieben.
