# MusicLab v0.9.2

## Neu

- FFmpeg/loudnorm-Auswertung grundlegend robuster gemacht.
- FFmpeg-`stderr` wird nicht mehr automatisch als Fehler behandelt.
- Der echte loudnorm-JSON-Block wird gezielt über `input_i`, `input_tp` und `input_lra` extrahiert.
- ID3-Private-Tags, ReplayGain-Ausgaben, Cover-Streams und normale FFmpeg-Metadaten erzeugen keine falschen Analysefehler mehr.
- Echte Fehler werden kompakter ausgegeben.
- Version auf v0.9.2 gesetzt.

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
