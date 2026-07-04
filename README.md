# MusicLab v1.0.2

Musikbibliothek scannen, analysieren und normalisieren.

## Änderungen v1.0.2

- DB-Schema-Kachel entfernt.
- Kompakte Anzeige für Backup-Modus und Parallelität in der Kopfstatistik.
- Zahnrad im Titelbereich entfernt, Einstellungen bleiben oben im Header.
- Titelauswahl in der Titeltabelle ergänzt.
- Einzelne oder mehrere ausgewählte Titel können normalisiert werden.
- Vorschau und Sicherheitsabfrage vor Titel-Normalisierung.

## Installation Synology

1. Inhalt nach `/volume1/docker/musiclab` kopieren.
2. Im Container Manager Projekt aus `docker-compose.yml` neu erstellen oder aktualisieren.
3. Browser hart neu laden.

## Hinweise

- `data/` ist enthalten und sollte bestehen bleiben.
- Für produktive Normalisierung Backup-Modus aktiv lassen.
