## v2.7.2

- Cover hinzufügen/entfernen im Tag-Grid repariert
- Mehrfachauswahl für Cover-Aktionen korrigiert
- Apple-Compilation-Metadaten nativ und verifiziert geschrieben
- erneutes Compilation-Anwenden erzwingt Apple-Reparatur
- strengere JPEG-Prüfung vor dem Einbetten

# MusicLab Changelog

## v2.7.1

- Apple-Music-Zusammenstellungen schreiben jetzt zusätzlich zum Compilation-Flag einen einheitlichen Albuminterpreten, ohne die Titelinterpreten zu verändern.
- Neuer Wartungsjob repariert die Tags bereits markierter Zusammenstellungen gesammelt.
- Der Cover-Wartungsjob findet Ordnercover über alle beteiligten Compilation-Ordner und bettet das gemeinsame Cover in jeden unterstützten Titel ein.
- Gleichnamige reguläre Alben verschiedener Künstler werden bei der Cover-Wartung getrennt behandelt.
- Parallele Normalisierung kann nun auch mit 6 oder 8 Workern gewählt werden.

## v2.7.0

### Lautstärkeanalyse

- Kombinierte EBU-R128-, Loudnorm- und Sample-Peak-Analyse pro Titel.
- Zusätzliche Messwerte für maximales Momentary LUFS, maximales Short-Term LUFS und Sample Peak.
- Automatische Parallelisierung passend zur verfügbaren CPU, standardmäßig auf acht Worker begrenzt.
- FFmpeg arbeitet pro Analysejob mit einem Thread, um Überbelegung bei parallelen Titeln zu vermeiden.
- Robuste Schema-Migration für bestehende MusicLab-Datenbanken.

## v2.6.1

### Tag-Tabelle

- Sortierung per Klick auf Interpret, Titel, Track, Track-Gesamtzahl, Album, CD, CD-Gesamtzahl, Genre, Jahr, "Verschiedene Interpreten" und Pfad.
- Drei Zustände je Spalte: aufsteigend, absteigend und keine Sortierung.
- Mehrfachsortierung mit Shift-Klick; kleine Zahlen zeigen die Reihenfolge der Sortierkriterien.
- Track-, CD- und Jahreswerte werden numerisch sortiert.
- Leere Werte bleiben unabhängig von der Sortierrichtung am Ende.
- Die Sortierung gilt für alle gefilterten Titel, nicht nur für die sichtbare Seite.
- Sortierung bleibt bei Filtern, Aktualisieren und Seitenwechsel erhalten und wird lokal im Browser gespeichert.

### Oberfläche

- Die Tabellenkachel nutzt den verbleibenden Platz bis fast an den unteren Rand.
- Sortierbare Überschriften besitzen klare Hover- und Aktivzustände.
- Tabellenkopf, Filterzeile, Scrollbereich und Seitennavigation bleiben erreichbar.

## v2.5.8

- Tag-Arbeitsbereich wird direkt unter der Filterleiste aufgespannt.
- Tabelle und Eigenschaftenbereich nutzen die restliche Fensterhöhe.
- Scrollbereich und Fußzeile bleiben vollständig erreichbar.

## v2.5.6

- Ruhige Datentabelle mit Bearbeitung per Doppelklick.
- Track- und CD-Nummern werden getrennt von der Gesamtzahl angezeigt.
- Einklappbare Eigenschaftenleiste und kompakterer Kopfbereich.
