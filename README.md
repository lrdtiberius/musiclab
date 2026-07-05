# MusicLab v1.5.16

Musikbibliothek analysieren, normalisieren, Tags bearbeiten und Medien durchsuchen.

## Neu in v1.5.16

- Coveranzeige liest jetzt ausschließlich eingebettete Cover aus den Audiodateien.
- `cover.jpg`/`folder.jpg` werden nicht mehr benötigt und von MusicLab nicht mehr erzeugt.
- Cover-Upload auf der Tags-Seite bettet das Bild in alle MP3s des Albumordners ein.
- Medienseite zeigt weiterhin einen Platzhalter, wenn wirklich kein eingebettetes Cover vorhanden ist.
- Backend benötigt weiterhin kein `python-multipart`.

## Installation Synology

1. Ordner nach `/volume1/docker/musiclab` kopieren.
2. Im Container Manager Projekt aus `docker-compose.yml` erstellen oder aktualisieren.
3. Container neu bauen/starten.

## Hinweise

- Der Musikpfad im Container ist standardmäßig `/music`.
- Der NAS-Musikordner wird in `docker-compose.yml` gemountet.
- Datenbank, Logs und Backups liegen in `/data`.


## Neu in v1.5.16
- Medienseite: Mehrfach-CD-Alben werden als ein Album zusammengefasst.
- Titelansicht gruppiert Disc 1 / Disc 2 / usw.
- Suche-X auf der Medienseite erneut zentriert.
