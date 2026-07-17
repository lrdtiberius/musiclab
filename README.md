# MusicLab v2.3.0

MusicLab ist eine Docker-basierte Musikverwaltung für NAS und Linux.

## Schnellstart
1. Release-ZIP entpacken.
2. Dateien nach `/volume1/docker/musiclab` kopieren.
3. Vorhandenen `data`-Ordner behalten.
4. Musikpfad in `docker-compose.yml` prüfen.
5. Projekt stoppen, bereinigen und neu erstellen.
6. `http://NAS-IP:8092` öffnen.

## Dokumentation
Vollständige Anleitung: `MusicLab_Benutzerhandbuch_v2.3.0.pdf`

## Wichtig
`data/musiclab.sqlite` bei Updates nicht löschen oder überschreiben.

## Credits
Idea & Umsetzung by Lrd.Tiberius


## Neue Normalisierung in v2.3.0

MusicLab verändert nur Titel, deren gemessene integrierte Lautheit außerhalb der eingestellten LUFS-Toleranz liegt. Die Pegeländerung ist konstant und verändert nicht die Lautstärkeverhältnisse innerhalb des Liedes. Positive Verstärkung wird am True-Peak-Ziel begrenzt; es wird kein dynamischer Limiter eingesetzt.

Vor dem Start kann unter Einstellungen - Audio eine CSV-Vorschau exportiert werden.


## Neu in v2.3.0

- Schaltfläche **Alle Backups wiederherstellen** unter Einstellungen -> Backup
- stellt pro Datei das neueste vorhandene Backup wieder her
- schneller atomarer Dateiaustausch ohne sofortige Neu-Analyse
- betroffene Analysewerte werden zurückgesetzt
- Backup-Dateien bleiben erhalten


## Neu in v2.3.0

Auf der Tags-Seite können Sampler und Alben mit mehreren Künstlern über eine Checkbox als „Verschiedene Interpreten“ markiert werden. Die einzelnen Titelinterpreten bleiben erhalten.


## Neu in v2.3.0

Die Titel-Tabelle unter Tags nutzt den verfügbaren Platz besser und besitzt größere, besser lesbare Zeilen und Eingabefelder.


## Neu in v2.3.0

- Tag-Interpreten werden beim Auswählen exakt nach Groß-/Kleinschreibung gefiltert.
- Falsch geschriebene Varianten wie `Die toten Hosen` können gezielt geöffnet und korrigiert werden.
- Die Signatur wurde dezent in die obere Navigation verschoben.
- Der Bereich `Titel-Tags` nutzt deutlich mehr der verfügbaren Fensterhöhe.
- Der Album-Bereich wurde leicht kompakter gestaltet.


## Neu in v2.3.0

- Der Bereich `Titel-Tags` füllt nun tatsächlich den gesamten verbleibenden Platz bis zum unteren Fensterrand.
- Das alte `main`-Grid wird im Tags-Modus deaktiviert; dadurch kann es die Höhe nicht mehr begrenzen.
- Nur die Titel-Tabelle scrollt.
- Alle sechs Protokollfilter sind exakt gleich breit und hoch.
- Aktivieren von `Tags`, `Audio` oder `Sortierung` verändert keine Abmessungen mehr.


## Neu in v2.3.0

- Coverfläche öffnet nur noch den Dateiauswahldialog.
- Das kleine X entfernt nur das eingebettete Cover.
- Vorschau wird erst nach erfolgreichem Speichern aktualisiert.
- robuste JPEG-Konvertierung mit Pillow und FFmpeg-Fallback.
- verständliche Fehler bei ungültigen Bildern.
- Titel-Tags und Protokollfilter weiter stabilisiert.


## Neu in v2.3.0

- Bei aktivierter Checkbox `Verschiedene Interpreten` wird der Albuminterpret automatisch gesetzt und gesperrt.
- Die einzelnen Titelinterpreten bleiben unverändert.
- Sampler werden beim automatischen Sortieren gemeinsam unter `Verschiedene Interpreten/Album` abgelegt.
- Die irreführende Meldung `Albumordner existierte bereits` wurde korrigiert.
- Die Rückmeldung nennt jetzt die Anzahl der tatsächlich verschobenen Dateien.
- Bereits Apple-kompatible eingebettete JPEG-Cover werden übersprungen.


## Neu in v2.3.0

- Vorhandene Zielordner gelten nicht mehr als Konflikt.
- Nur bereits vorhandene Zieldateien mit identischem Zielpfad sind echte Konflikte.
- Konfliktdateien werden sicher übersprungen und nicht als `(Duplikat)` verschoben.
- Wiederholte Sortiervorschauen sind idempotent und zeigen nur echte ausstehende Verschiebungen.
- Vorschau trennt sichere Verschiebungen, bereits korrekte Dateien, Konflikte und fehlende Dateien.
- Sortierungsprotokoll wird bei Vorschau, Start, Fortschritt, Abschluss und Export geschrieben.
- Nach dem Start öffnet MusicLab automatisch den Protokollfilter `Sortierung`.


## Neu in v2.3.0

- Album-Cover und Albumfelder stehen auf breiten Fenstern nebeneinander.
- Der Album-Tags-Bereich ist dadurch deutlich kompakter.
- Titel-Tags erhält je nach Fensterhöhe mindestens 300 bis 360 Pixel.
- Nur die Titeltabelle scrollt; die Albumdaten bleiben sichtbar.


## Neu in v2.3.0

- Tags-Seite vollständig auf Flexbox umgestellt.
- Album-Tags nutzt nur noch die tatsächliche Inhaltshöhe.
- Titel-Tags erhält den kompletten verbleibenden Fensterplatz.
- Coverbereich deutlich kompakter.
- Nur die Titeltabelle scrollt.
- Sticky Tabellenkopf im Titelbereich.
- Saubere Anpassung für niedrige und schmale Fenster.


## Neu in v2.3.0

- ältere Mindesthöhen werden durch eine eindeutige Desktop-Aufteilung überschrieben
- Album-Tags ist auf 228–238 Pixel begrenzt
- Titel-Tags erhält mindestens 300 Pixel, bei hohen Fenstern mindestens 360 Pixel
- Tags-Seite nutzt die reale Viewport-Höhe


## Neu in v2.3.0

- eigentliche Ursache behoben: `tagsMode` wurde beim Wechsel auf die Tags-Seite nie am Body gesetzt
- dadurch waren sämtliche früheren Tags-Höhenregeln wirkungslos
- `setAppView()` setzt und entfernt `tagsMode` jetzt korrekt
- zusätzlicher direkter CSS-Fallback auf `#tagsView.appView.active`
- Titel-Tags erhält bei großen Fenstern mindestens 390 Pixel


## Neu in v2.3.0

- `Alles normalisieren` speichert die aktuell sichtbaren Einstellungen automatisch.
- Vorschau und Job erhalten denselben unveränderlichen Einstellungsschnappschuss.
- Ziel-LUFS, True Peak, Toleranz und LRA werden vor dem Start abgeglichen.
- Bei einer Abweichung wird die Normalisierung mit HTTP 409 sicher blockiert.
- Der Bestätigungsdialog zeigt einen Prüfcode der verwendeten Einstellungen.
- Das Protokoll nennt Werte und Prüfcode des tatsächlich gestarteten Jobs.


## Neu in v2.3.0

- Compilation-Verhalten an Apple Music angeglichen.
- Die Checkbox setzt ein echtes Compilation-Flag.
- Individuelle Titelinterpreten bleiben unverändert.
- Der Albumartist darf bei Compilations leer bleiben.
- MusicLab zeigt das Album trotzdem virtuell als `Verschiedene Interpreten` an.
- Beim Sortieren werden solche Alben unter `Verschiedene Interpreten/Album` zusammengeführt.
- Die Tags-Oberfläche verwendet nun `Albuminterpret` und `Compilation-Album`.
