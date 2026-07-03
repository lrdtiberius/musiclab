# MusicLab v0.3.0

LUFS-Analyse (EBU R128) als nächster großer Schritt.

## Neu

- Analyse-Tabelle in SQLite (`analysis`)
- `ffmpeg loudnorm=print_format=json` pro Titel
- Albumanalyse über Button **Album analysieren**
- Gesamtanalyse über **Alles analysieren**
- Anzeige pro Track:
  - Integrated LUFS
  - True Peak
  - LRA
- Album-Zusammenfassung:
  - analysiert x/y
  - Durchschnitts-LUFS
  - Max True Peak
  - Durchschnitts-LRA
- Docker Compose mountet Frontend und Backend-Code direkt zum leichteren Entwickeln.

## Wichtig

Die Analyse ist noch lesend. Es wird noch nichts normalisiert oder überschrieben.

## Installation Synology

1. Inhalt der ZIP nach `/volume1/docker/musiclab` kopieren.
2. Container Manager: Projekt stoppen.
3. Bereinigen.
4. Neu erstellen/starten.
5. Browser hart neu laden: `Cmd + Shift + R` oder `http://NAS-IP:8092/?v=030`.
6. Ein Album auswählen und **Album analysieren** klicken.

Falls Backend-Code nicht aktualisiert wirkt: Backend-Container neu starten.
