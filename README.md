# MusicLab v2.7.2

MusicLab analysiert, normalisiert und verwaltet eine lokale Musikbibliothek.


## Neu in v2.7.2

- Cover hinzufügen auf der neuen tabellarischen Tags-Seite repariert.
- Cover entfernen verwendet jetzt ausschließlich die tatsächlich ausgewählten bzw. fokussierten Audiodateien.
- Mehrfachauswahl funktioniert auch ohne zuvor separat fokussierten Titel.
- Apple-Compilation-Metadaten werden formatnativ geschrieben und anschließend geprüft.
- MP3: TCMP + TPE2; M4A/MP4: cpil + aART; FLAC/Ogg: compilation + albumartist.
- Erneutes Anwenden von `Compilation / verschiedene Interpreten` erzwingt eine Reparatur der Apple-Metadaten.

## Neu in v2.7.1

- Zuverlässige Gruppierung von Zusammenstellungen in Apple Music durch Compilation-Flag plus gemeinsamen Albuminterpreten.
- Wartungsjob zur Reparatur vorhandener Zusammenstellungen.
- Albumweit konsistente, Apple-kompatible Cover-Einbettung für alle Titel.
- Parallele Normalisierung mit bis zu 8 Workern.

## Neu in v2.7.0

- Erweiterte Lautstärkeanalyse: Integrated LUFS, True Peak, LRA, Momentary-Maximum, Short-Term-Maximum und Sample Peak in einem FFmpeg-Durchlauf.
- Automatische, CPU-begrenzte Parallelisierung (standardmäßig bis zu 8 Worker, per `ANALYSIS_MAX_WORKERS` konfigurierbar).
- Bestehende Datenbanken werden automatisch um die neuen Analysewerte erweitert.

## Neu in v2.6.1

- Sortierung über die Spaltenüberschriften der Tag-Tabelle.
- Aufsteigend, absteigend oder unsortiert per wiederholtem Klick.
- Mehrfachsortierung mit Shift-Klick.
- Numerische Sortierung für Track, Gesamttracks, CD, Gesamt-CDs und Jahr.
- Sortierung über die vollständige gefilterte Bibliothek, nicht nur die aktuelle Seite.
- Sortierung bleibt beim Filtern, Aktualisieren und Blättern erhalten.
- Vergrößerter Tabellenbereich bis fast an den unteren Fensterrand.

Vollständige Anleitung: `MusicLab_Benutzerhandbuch_v2.6.1.pdf`
