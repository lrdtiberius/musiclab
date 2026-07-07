# MusicLab v1.8.8

Bugfix-Version auf Basis deiner v1.8.0-Linie.

## Neu in v1.8.8

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
