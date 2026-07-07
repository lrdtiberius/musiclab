# MusicLab v1.8.7

Bugfix-/Komfortversion auf Basis von v1.8.0.

## Neu in v1.8.7

- Cover speichern repariert: virtuelle Album-Auswahl wird auf echten Albumordner aufgelöst.
- Cover werden nicht mehr nur in MP3 geschrieben, sondern auch in M4A/AAC, FLAC und OGG/Vorbis, soweit Mutagen das Format unterstützt.
- Die Rückmeldung zeigt jetzt Dateien statt nur MP3-Dateien.


- Duplikat-Treffer zeigen jetzt pro Datei Aktionen:
  - **Pfad öffnen**: öffnet den Ordner per `smb://` und kopiert den NAS-Pfad als Fallback in die Zwischenablage.
  - **Pfad kopieren**: kopiert den NAS-Pfad.
- Bei echten Duplikaten gibt es **Kein Duplikat bestätigen**.
  - Der Treffer wird dauerhaft in der MusicLab-Datenbank gespeichert und danach ausgeblendet.
  - Dateien werden dabei nicht verändert oder gelöscht.
- Backend-Endpunkte:
  - `GET /api/path_info?path=...`
  - `POST /api/duplicates/confirm`
  - `GET /api/duplicates/confirmed`
  - `DELETE /api/duplicates/confirmed`
- Duplikatregel bleibt: gleicher Interpret + gleiches Album + mindestens 90 % ähnlicher Titel.
- Audio-Tab enthält nochmals härtere Flächen-/Kachel-Regeln und Cache-Buster `?v=1.8.7`.

## SMB-Hinweis

Standardannahme aus der Docker-Compose:

- Container: `/music`
- NAS: `/volume1/DS420/Musik`
- SMB-Link: `smb://<NAS-IP>/DS420/Musik/...`

Falls deine SMB-Freigabe anders heißt, kann sie im Backend per Environment angepasst werden:

- `SMB_SHARE`, Standard: `DS420`
- `SMB_PREFIX`, Standard: `Musik`
- `SMB_ALT_SHARE`, Standard: `Musik`
- `NAS_MUSIC_PATH`, Standard: `/volume1/DS420/Musik`

## Credits

Idea & Umsetzung by Lrd.Tiberius.


## v1.8.7

- Pfad öffnen bei Duplikaten robuster gemacht: einstellbare SMB-Basis, SMB-Link kopieren und Finder-Befehl kopieren.
- Einstellung `SMB-Basis für Finder`, z.B. `smb://DS923/Musik` oder `smb://192.168.178.50/Musik`.
- Direkter Browser-Open bleibt verfügbar, aber mit Hinweis, falls Safari/Chrome es blockiert.
