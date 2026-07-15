# MusicLab v2.1.8

MusicLab ist eine Docker-basierte Musikverwaltung für NAS und Linux.

## Schnellstart
1. Release-ZIP entpacken.
2. Dateien nach `/volume1/docker/musiclab` kopieren.
3. Vorhandenen `data`-Ordner behalten.
4. Musikpfad in `docker-compose.yml` prüfen.
5. Projekt stoppen, bereinigen und neu erstellen.
6. `http://NAS-IP:8092` öffnen.

## Dokumentation
Vollständige Anleitung: `MusicLab_Benutzerhandbuch_v2.1.8.pdf`

## Wichtig
`data/musiclab.sqlite` bei Updates nicht löschen oder überschreiben.

## Credits
Idea & Umsetzung by Lrd.Tiberius


## Neue Normalisierung in v2.1.8

MusicLab verändert nur Titel, deren gemessene integrierte Lautheit außerhalb der eingestellten LUFS-Toleranz liegt. Die Pegeländerung ist konstant und verändert nicht die Lautstärkeverhältnisse innerhalb des Liedes. Positive Verstärkung wird am True-Peak-Ziel begrenzt; es wird kein dynamischer Limiter eingesetzt.

Vor dem Start kann unter Einstellungen - Audio eine CSV-Vorschau exportiert werden.


## Neu in v2.1.8

- Schaltfläche **Alle Backups wiederherstellen** unter Einstellungen -> Backup
- stellt pro Datei das neueste vorhandene Backup wieder her
- schneller atomarer Dateiaustausch ohne sofortige Neu-Analyse
- betroffene Analysewerte werden zurückgesetzt
- Backup-Dateien bleiben erhalten


## Neu in v2.1.8

Auf der Tags-Seite können Sampler und Alben mit mehreren Künstlern über eine Checkbox als „Verschiedene Interpreten“ markiert werden. Die einzelnen Titelinterpreten bleiben erhalten.


## Neu in v2.1.8

Die Titel-Tabelle unter Tags nutzt den verfügbaren Platz besser und besitzt größere, besser lesbare Zeilen und Eingabefelder.


## Neu in v2.1.8

- Tag-Interpreten werden beim Auswählen exakt nach Groß-/Kleinschreibung gefiltert.
- Falsch geschriebene Varianten wie `Die toten Hosen` können gezielt geöffnet und korrigiert werden.
- Die Signatur wurde dezent in die obere Navigation verschoben.
- Der Bereich `Titel-Tags` nutzt deutlich mehr der verfügbaren Fensterhöhe.
- Der Album-Bereich wurde leicht kompakter gestaltet.


## Neu in v2.1.8

- Der Bereich `Titel-Tags` füllt nun tatsächlich den gesamten verbleibenden Platz bis zum unteren Fensterrand.
- Das alte `main`-Grid wird im Tags-Modus deaktiviert; dadurch kann es die Höhe nicht mehr begrenzen.
- Nur die Titel-Tabelle scrollt.
- Alle sechs Protokollfilter sind exakt gleich breit und hoch.
- Aktivieren von `Tags`, `Audio` oder `Sortierung` verändert keine Abmessungen mehr.


## Neu in v2.1.8

- Coverfläche öffnet nur noch den Dateiauswahldialog.
- Das kleine X entfernt nur das eingebettete Cover.
- Vorschau wird erst nach erfolgreichem Speichern aktualisiert.
- robuste JPEG-Konvertierung mit Pillow und FFmpeg-Fallback.
- verständliche Fehler bei ungültigen Bildern.
- Titel-Tags und Protokollfilter weiter stabilisiert.


## Neu in v2.1.8

- Bei aktivierter Checkbox `Verschiedene Interpreten` wird der Albuminterpret automatisch gesetzt und gesperrt.
- Die einzelnen Titelinterpreten bleiben unverändert.
- Sampler werden beim automatischen Sortieren gemeinsam unter `Verschiedene Interpreten/Album` abgelegt.
- Die irreführende Meldung `Albumordner existierte bereits` wurde korrigiert.
- Die Rückmeldung nennt jetzt die Anzahl der tatsächlich verschobenen Dateien.
- Bereits Apple-kompatible eingebettete JPEG-Cover werden übersprungen.


## Neu in v2.1.8

- Vorhandene Zielordner gelten nicht mehr als Konflikt.
- Nur bereits vorhandene Zieldateien mit identischem Zielpfad sind echte Konflikte.
- Konfliktdateien werden sicher übersprungen und nicht als `(Duplikat)` verschoben.
- Wiederholte Sortiervorschauen sind idempotent und zeigen nur echte ausstehende Verschiebungen.
- Vorschau trennt sichere Verschiebungen, bereits korrekte Dateien, Konflikte und fehlende Dateien.
- Sortierungsprotokoll wird bei Vorschau, Start, Fortschritt, Abschluss und Export geschrieben.
- Nach dem Start öffnet MusicLab automatisch den Protokollfilter `Sortierung`.
