# MusicLab v2.1.1

MusicLab ist eine Docker-basierte Musikverwaltung für NAS und Linux.

## Schnellstart
1. Release-ZIP entpacken.
2. Dateien nach `/volume1/docker/musiclab` kopieren.
3. Vorhandenen `data`-Ordner behalten.
4. Musikpfad in `docker-compose.yml` prüfen.
5. Projekt stoppen, bereinigen und neu erstellen.
6. `http://NAS-IP:8092` öffnen.

## Dokumentation
Vollständige Anleitung: `MusicLab_Benutzerhandbuch_v2.1.1.pdf`

## Wichtig
`data/musiclab.sqlite` bei Updates nicht löschen oder überschreiben.

## Credits
Idea & Umsetzung by Lrd.Tiberius


## Neue Normalisierung in v2.1.1

MusicLab verändert nur Titel, deren gemessene integrierte Lautheit außerhalb der eingestellten LUFS-Toleranz liegt. Die Pegeländerung ist konstant und verändert nicht die Lautstärkeverhältnisse innerhalb des Liedes. Positive Verstärkung wird am True-Peak-Ziel begrenzt; es wird kein dynamischer Limiter eingesetzt.

Vor dem Start kann unter Einstellungen - Audio eine CSV-Vorschau exportiert werden.


## Neu in v2.1.1

- Schaltfläche **Alle Backups wiederherstellen** unter Einstellungen -> Backup
- stellt pro Datei das neueste vorhandene Backup wieder her
- schneller atomarer Dateiaustausch ohne sofortige Neu-Analyse
- betroffene Analysewerte werden zurückgesetzt
- Backup-Dateien bleiben erhalten
