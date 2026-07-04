# MusicLab v0.9.1

## Neu

- Log-Export direkt aus der Oberfläche:
  - gesamtes Log exportieren
  - nur Fehler exportieren
  - Log löschen
- Backend schreibt Logs zusätzlich dauerhaft nach `/data/logs/musiclab.log`.
- Logrotation bei ca. 10 MB.
- Analyse-Fehler werden kompakter behandelt; FFmpeg-Ausgaben werden robuster gelesen.
- Version auf v0.9.1 gesetzt.

## Installation Synology

Ordnerinhalt nach `/volume1/docker/musiclab` kopieren.

Wichtige Struktur:

```text
/volume1/docker/musiclab/backend
/volume1/docker/musiclab/frontend
/volume1/docker/musiclab/data
/volume1/docker/musiclab/docker-compose.yml
```

Danach Container-Projekt neu starten und Browser hart neu laden.
