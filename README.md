# MusicLab v1.5.5

Musikbibliothek analysieren, normalisieren, Tags bearbeiten und Medien durchsuchen.

## Neu in v1.5.5

- Medien-Seite überarbeitet als Browser **Interpret → Album → Titel**.
- Linke Audio-/Tags-Suche wird auf der Medien-Seite ausgeblendet.
- Sortierung der Medienansicht nach **Interpret** oder **Album**.
- Albumliste zeigt Coverbilder, wenn sie in den Dateien vorhanden sind.
- Albumdetails zeigen Cover, Titel, Dauer, Bitrate und Pfad.
- Download-Button bleibt für Albumordner als ZIP erhalten.

## Installation Synology

1. Ordner nach `/volume1/docker/musiclab` kopieren.
2. Im Container Manager Projekt aus `docker-compose.yml` erstellen oder aktualisieren.
3. Container neu bauen/starten.

## Hinweise

- Der Musikpfad im Container ist standardmäßig `/music`.
- Der NAS-Musikordner wird in `docker-compose.yml` gemountet.
- Datenbank, Logs und Backups liegen in `/data`.
