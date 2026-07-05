# MusicLab v1.5.0

Musikbibliothek analysieren, normalisieren und Tags bearbeiten.

## Neu in v1.5.0

- Neue Hauptseite **Medien** mit Datenbankübersicht der lokalen Bibliothek.
- Album-Download vorbereitet: Download erzeugt ein ZIP des Albumordners.
- Option in **Einstellungen → Tags & Sortierung**: Dateien nach Tag-Änderung sortieren.
- Sortierschema: `Interpret/Album/Titel.ext`.
- Dateiname entspricht dem Tracktitel.
- Bestehende Dateien werden nicht überschrieben, sondern als `Duplikat` gekennzeichnet.
- Wenn ein Ziel-Albumordner bereits existiert, wird dies im Ergebnis/Log berücksichtigt.

## Installation Synology

1. Ordner nach `/volume1/docker/musiclab` kopieren.
2. Im Container Manager Projekt aus `docker-compose.yml` erstellen oder aktualisieren.
3. Container neu bauen/starten.

## Hinweise

- Der Musikpfad im Container ist standardmäßig `/music`.
- Der NAS-Musikordner wird in `docker-compose.yml` gemountet.
- Datenbank, Logs und Backups liegen in `/data`.
