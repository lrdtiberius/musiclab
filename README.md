# MusicLab v1.8.10


## v1.8.10

- Cover-Vorschau in Tags repariert: Beim Albumwechsel wird das alte Cover sofort entfernt.
- `#tagCoverPreview` behält jetzt dauerhaft seine ID; dadurch kann die Vorschau nach dem ersten geladenen Cover weiter ersetzt werden.
- Medien-Albumkopf wird beim Albumwechsel sofort geleert, damit kein altes Cover während des Ladens stehen bleibt.

Bugfix-Version auf Basis deiner v1.8.0-Linie.

## Neu in v1.8.10

### Cover speichern korrigiert

- Das Frontend sendet beim Cover-Speichern jetzt die **konkreten sichtbaren Track-Pfade** an das Backend.
- Dadurch wird nicht mehr nur anhand von Albumname/virtueller Auswahl geraten.
- Das verhindert falsche Treffer bei:
  - doppelten Albumnamen,
  - Compilations,
  - virtuellen `__album__:`-Auswahlen,
  - abweichendem Ordnernamen vs. Album-Tag.
- Nach dem Speichern wird das Cover direkt erneut mit Cache-Buster geladen.
- Die Rückmeldung zeigt jetzt:
  - eingebettete Dateien,
  - geprüfte Dateien,
  - Ordnercover-Dateien,
  - Fehler.
- Zusätzlich zum Einbetten wird als Kompatibilitäts-Fallback ein `cover.jpg`/`folder.jpg` bzw. `cover.png`/`folder.png` im echten Albumordner gespeichert.

### Weiterhin enthalten

- CREDITS.md enthalten.
- Duplikat-Treffer können als „kein Duplikat“ bestätigt werden.
- Duplikatregel: gleicher Interpret + gleiches Album + mindestens 90 % ähnlicher Titel.
- Pfad-/SMB-Helfer für Duplikate.
- Audio-/Media-/Tags-/Protokoll-/Einstellungen-Ansichten aus der v1.8er-Linie.

## Wichtig beim Update

Nach dem Einspielen:

```bash
docker compose down
docker compose up -d --build
```

Danach im Browser einmal hart neu laden, damit Safari/Chrome keine alte `app.js`/`styles.css` nutzt.

## Credits

Idea & Umsetzung by Lrd.Tiberius.


## v1.8.10
- Fehler `renderCheckList` in der Duplikatprüfung behoben.
- Cover-Speichern zeigt nun die konkret bearbeiteten Track-Pfade im Backend-Ergebnis und aktualisiert die Vorschau gezielt.