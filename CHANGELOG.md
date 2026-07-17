# Changelog

## v2.2.3

- kritischen Einstellungs-Synchronisationsfehler vor `Alles normalisieren` behoben
- aktuelle UI-Werte werden vor der Vorschau automatisch gespeichert
- Vorschau und Worker verwenden denselben Snapshot
- Sicherheitsabbruch bei abweichendem Prüfcode
- verbindliche Werte im Bestätigungsdialog und Protokoll



## v2.2.3

- fehlende Aktivierung von `body.tagsMode` behoben
- bisher wirkungslose Tags-CSS-Regeln werden nun tatsächlich angewendet
- direkter CSS-Fallback für das aktive Tags-View
- Titel-Tags sichtbar und dauerhaft vergrößert



## v2.2.3

- endgültiger Höhenfix für Titel-Tags
- Album-Tags auf feste kompakte Desktop-Höhe begrenzt
- Tags-Seite direkt an Viewport-Höhe gekoppelt
- ältere konkurrierende min-height-Regeln zuverlässig überschrieben



## v2.2.3

- Tags-Layout komplett refaktoriert
- Album-Tags auf echte Inhaltshöhe reduziert
- Titel-Tags füllt den gesamten restlichen Fensterplatz
- kompakteres Cover- und Formularlayout
- sticky Tabellenkopf
- responsive Anpassung für niedrige und schmale Fenster



## v2.2.3

- Album-Tags-Layout auf Desktop kompakter angeordnet
- Cover und Albumfelder nebeneinander
- Titel-Tags-Bereich deutlich vergrößert
- Fensterhöhe wird zuverlässiger ausgenutzt



## v2.2.3

- echte Dateikonflikte statt vorhandener Ordner zählen
- Konflikte sicher überspringen, keine automatischen Duplikatnamen
- idempotente Sortiervorschau
- detaillierte Vorschau-Statistik
- Sortierungslog vollständig repariert
- Sortier-CSV enthält Verschiebungen und Konflikte



## v2.2.3

- Albuminterpret bei Samplern automatisch `Verschiedene Interpreten`
- individuelles Interpret-Feld während der Samplerkennzeichnung gesperrt
- Sampler-Sortierung nach Albumartist statt Titelartist
- präzise Anzeige tatsächlich verschobener Dateien
- falsche Meldung zu bereits vorhandenen Albumordnern behoben
- bereits Apple-kompatible JPEG-Cover werden nicht erneut eingebettet



## v2.2.3

- Cover-Auswahl und Cover-Löschen getrennt
- robuste JPEG-Konvertierung
- Covervorschau erst nach erfolgreichem Upload
- größere Titel-Tags-Fläche
- identische Protokollfilter in Safari



## v2.2.3

- Titel-Tags nutzen die vollständige verbleibende Fensterhöhe
- altes Main-Grid im Tags-Modus neutralisiert
- alle Protokollfilter mit identischer Breite und Höhe
- keine Größenänderung beim Umschalten der Filter



## v2.2.3

- exakte, case-sensitive Auswahl von Interpreten im Tag-Editor
- falsche Schreibweisen bleiben gezielt bearbeitbar
- Signatur dezent in die obere Navigation verschoben
- deutlich größerer Titel-Tags-Bereich
- kompakterer Album-Tags-Bereich


## v2.2.3

- Titel-Tabelle auf der Tags-Seite vergrößert
- größere Eingabefelder und Schrift für Titel, Interpret, Track und Disc
- verbleibender Platz nach unten wird besser genutzt
- kompaktere Darstellung bei niedrigen Browserfenstern

## v2.2.3

- Checkbox „Album als Verschiedene Interpreten anzeigen“ auf der Tags-Seite
- schreibt Album Artist und Compilation-Flag in unterstützte Formate
- individuelle Titelinterpreten bleiben erhalten
- markierte Alben erscheinen gebündelt unter „Verschiedene Interpreten“

## v2.2.3

- schnelle Wiederherstellung aller vorhandenen Backups
- Vorschau mit Dateianzahl, Größe und fehlenden Backups
- je Datei wird das neueste Backup verwendet
- Backups bleiben nach der Wiederherstellung bestehen
- Analysewerte der wiederhergestellten Titel werden sicher zurückgesetzt

## v2.2.3
- sichere statische Pegelanpassung statt dynamischem loudnorm bei der Normalisierung
- einstellbare LUFS-Toleranz (Standard ±1,5 LUFS)
- nur Titel außerhalb der Toleranz werden verändert
- positive Verstärkung wird ohne Limiter am True-Peak-Ziel begrenzt
- CSV-Export der vollständigen Normalisierungs-Vorschau
- bestehende Scan-, Tag-, Cover- und Layoutverbesserungen bleiben erhalten

## v2.0.1
- Benutzerhandbuch und bereinigtes Release-Paket
