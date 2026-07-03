# MusicLab v0.2

MusicLab ist ein selbstgehosteter Musik-Manager für Synology/Docker.

## v0.2

- Scanner neu aufgebaut
- SQLite-Schema v2
- eindeutige Tracks über `path UNIQUE`
- Tracknummern normalisiert (`1`, `01`, `1/12`, `1/0` -> `1`)
- Discnummern vorbereitet
- kompletter Rebuild der Track-Datenbank bei Scan
- bessere Album-/Track-Anzeige mit Dateipfad

## Installation Synology

1. Inhalt dieses Ordners nach `/volume1/docker/musiclab` kopieren.
2. Im Container Manager Projekt aus diesem Ordner erstellen.
3. Projekt erstellen/starten.
4. Frontend: `http://NAS-IP:8092`
5. Backend: `http://NAS-IP:8091/api/health`

## Wichtig beim Update von v0.1

v0.2 baut die Datenbank beim nächsten Scan neu auf. Falls DSM alte Images cached:

1. Projekt stoppen
2. Aktion → Bereinigen
3. Alte Images `musiclab-backend` und `musiclab-frontend` löschen
4. Projekt neu erstellen/starten
5. Im Frontend auf **Bibliothek neu scannen** klicken

Musikpfad in `docker-compose.yml`:

```yaml
- /volume1/DS420/Musik:/music
```
