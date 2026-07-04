# MusicLab v1.0.0

Stabile Version mit Batch-Analyse, Batch-Normalisierung, Referenzalbum, Logexport, Stop-Button, Parallel-Analyse und Historie/Wiederherstellen.

## Installation Synology

1. Ordner nach `/volume1/docker/musiclab` kopieren.
2. Im Container Manager Projekt aus diesem Ordner erstellen oder aktualisieren.
3. Wichtig bei Synology: alte Images/Container ggf. löschen, wenn Änderungen nicht sichtbar werden.
4. Frontend ist auf Port `8092`, Backend auf Port `8091`.

## Neu in v1.0.0

- Einstellungen über Zahnrad-Dialog.
- Hauptansicht aufgeräumt: Zielwerte/Backup/Parallelität werden kompakt angezeigt.
- Historie für Normalisierungen.
- Wiederherstellen aus Backups direkt aus MusicLab.
- Backup-Modus bleibt wählbar: `/data/backups`, `.bak daneben`, oder aus.
- Schnellscan bleibt erhalten: unveränderte Analysewerte werden nicht gelöscht.
- Keine Statistik-Seite.

## Hinweis

Wiederherstellen funktioniert nur für Normalisierungen, bei denen ein Backup erstellt wurde.
