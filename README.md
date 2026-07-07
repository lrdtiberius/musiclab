# MusicLab v1.8.15

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
