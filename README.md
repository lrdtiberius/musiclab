# MusicLab v1.9.35 Synology Project Safe

Diese Version ist bewusst für deinen gewohnten Synology-Ablauf gebaut:

```text
Projekt stoppen → bereinigen → neu erstellen
```

## Wichtigste Änderung

Das Frontend wird nicht mehr fest in ein eigenes Docker-Image kopiert, sondern per Bind-Mount aus dem NAS-Ordner geladen:

```yaml
/volume1/docker/musiclab/frontend:/usr/share/nginx/html:ro
/volume1/docker/musiclab/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro
```

Das Backend-App-Verzeichnis wird ebenfalls gemountet:

```yaml
/volume1/docker/musiclab/backend/app:/app/app:ro
```

Dadurch verwendet der Container nach dem Neu-Erstellen direkt die Dateien, die du nach `/volume1/docker/musiclab` kopiert hast. Synology kann dadurch nicht mehr still ein altes Frontend-Image weiterverwenden.

## Enthalten

```text
docker-compose.yml
install_musiclab_ssh.sh
frontend/
backend/
data/
README.md
CREDITS.md
```

## Nicht mehr enthalten

```text
docker-compose.dev-volumes.example.yml
docker-compose.override.yml
update_musiclab.sh
__pycache__/
*.pyc
.DS_Store
```

## Installation

ZIP direkt nach `/volume1/docker/musiclab` entpacken/kopieren.

Empfohlen: `data/` nicht löschen, sonst geht die Datenbank mit Analysewerten verloren.

Danach entweder wie gewohnt im Synology Container Manager:

```text
Projekt stoppen → bereinigen → neu erstellen
```

oder per SSH:

```bash
cd /volume1/docker/musiclab
chmod +x install_musiclab_ssh.sh
./install_musiclab_ssh.sh
```

Danach öffnen:

```text
http://192.168.188.34:8092/?v=1913
```


## Hinweis zu data/

`data/.keep` ist enthalten, damit der Ordner sicher mit in der ZIP landet. Eine vorhandene `data/musiclab.sqlite` auf der NAS nicht löschen, wenn Analysewerte erhalten bleiben sollen.


## Änderungen in v1.9.35

- Batch-Button `Ausführen` bleibt nach Auswahl einer Aktion aktiv und wird nicht mehr vom Status-Poller grundlos ausgegraut.
- Dropdown `Aktion wählen…` aktualisiert den Button sofort per `onchange`.
- Die Arbeitsfläche unter den Tabs skaliert dynamisch anhand der echten Header-Höhe.
- Synology-Projektmodus bleibt erhalten.


## Änderungen in v1.9.35

- Backend-Fehler `name 'normalize_parallelism' is not defined` vollständig behoben.
- Alter Aufruf `normalize_parallelism()` bekommt einen Kompatibilitätswrapper.
- Parallelität wird aus `parallel_normalize` gelesen und auf sichere Werte begrenzt.


## Änderungen in v1.9.35

- Tag-Speichern lädt nicht mehr jedes Mal synchron Statistik, Genres, Browser und Tagseite komplett neu.
- Albumwechsel in der Tag-Ansicht lädt nicht mehr unnötig die Seitenleiste neu.
- Cover-Speichern aktualisiert die Vorschau direkt statt die komplette Tagseite neu zu laden.
- SQLite nutzt Timeout/WAL/busy_timeout gegen kurze `database is locked`-Phasen.
- CSS-Containment verbessert Scroll-/Render-Performance großer Listen.


## Änderungen in v1.9.35

- Cover werden vor dem Speichern Apple-kompatibel als JPEG/RGB normalisiert.
- Maximale Covergröße ca. 1200 × 1200 px.
- MP3-Cover werden als APIC `image/jpeg` gespeichert.
- MP3 wird mit ID3v2.3 gespeichert, was für Apple Musik oft zuverlässiger ist.
- M4A/ALAC/MP4-Cover werden als `covr`-Atom gespeichert.
- FLAC-Cover werden als Picture Block gespeichert.
- Zusätzlich werden `cover.jpg` und `folder.jpg` im Albumordner geschrieben.
- Nach dem Speichern wird geprüft, bei wie vielen Dateien wirklich ein Cover eingebettet ist.

Hinweis: Für bereits in Apple Musik importierte Dateien das Album ggf. aus der Mediathek entfernen und neu importieren, damit Apple die geänderten eingebetteten Cover neu einliest.


## Änderungen in v1.9.35

- Neuer Job: `Alle Cover Apple-kompatibel neu einbetten`.
- Der Job sucht pro Album vorhandene Cover aus `cover.jpg`, `folder.jpg` oder eingebetteten Covern.
- Gefundene Cover werden als JPEG/sRGB normalisiert und in alle unterstützten Dateien neu eingebettet.
- Zusätzlich werden `cover.jpg` und `folder.jpg` geschrieben.
- Fortschritt und Ergebnis erscheinen im Live-Log.

Hinweis für Apple Musik: Bereits importierte Alben müssen oft aus der Mediathek entfernt und neu importiert werden, damit Apple die neu eingebetteten Cover einliest.


## Änderungen in v1.9.35

- Neuer Job: `Alle Cover Apple-kompatibel neu einbetten`.
- Der Job sucht pro Album vorhandene Cover aus `cover.jpg`, `folder.jpg` oder eingebetteten Covern.
- Gefundene Cover werden als JPEG/sRGB normalisiert und in alle unterstützten Dateien neu eingebettet.
- Zusätzlich werden `cover.jpg` und `folder.jpg` geschrieben.
- Fortschritt und Ergebnis erscheinen im Live-Log.

Hinweis für Apple Musik: Bereits importierte Alben müssen oft aus der Mediathek entfernt und neu importiert werden, damit Apple die neu eingebetteten Cover einliest.


## Änderungen in v1.9.35

- Backend startet auch ohne installiertes `Pillow/PIL`.
- Cover-Konvertierung nutzt optional Pillow, sonst ffmpeg-Fallback.
- Kein harter `from PIL import Image`-Import mehr beim Start.


## Änderungen in v1.9.35

- Backend-Startfehler `NameError: name 'List' is not defined` behoben.
- `typing`-Importe für `Optional`, `List`, `Dict`, `Any` ergänzt.
- Zusätzlich `from __future__ import annotations`, damit Typ-Hinweise das Backend nicht mehr beim Start stoppen.
- Pillow bleibt optional mit Fallback.


## Änderungen in v1.9.35

- Button `Alle Cover Apple-kompatibel neu einbetten` ist jetzt auf der Einstellungsseite unter `Tags & Sortierung`.
- Der Cover-Neueinbettungsjob wurde robust ohne fehleranfällige Typ-Hinweise neu eingebaut.
- Preview- und Start-Endpunkt wurden stabilisiert.
- Nach Start springt MusicLab ins Protokoll, damit der Fortschritt sichtbar ist.


## Änderungen in v1.9.35

- Apple-Cover-Button hart aus Dashboard/globaler Position entfernt.
- Button fest unter Einstellungen → Tags & Sortierung eingefügt.
- Start funktioniert auch dann, wenn die Vorschau fehlschlägt.
- Endpunkte/Worker bleiben robust.


## Änderungen in v1.9.35

- Apple-Cover-Button vollständig aus globaler Position entfernt.
- Button erscheint nur noch in Einstellungen → Tags & Sortierung neben den Sortier-Buttons.


## Änderungen in v1.9.35

- Cover-Job-Fehler `name 'AUDIO_EXTS' is not defined` behoben.
- Robuster Fallback für Audio-Dateiendungen ergänzt.
- Cover-Job nutzt jetzt `is_musiclab_audio_file()` statt direkt auf `AUDIO_EXTS` zuzugreifen.
- Button-Platzierung aus v1.9.35 bleibt erhalten.


## Änderungen in v1.9.35

- Cover-Erkennung für Apple-Neueinbettung deutlich verbessert.
- Ordnercover werden case-insensitive und mit mehr Namen erkannt: cover, folder, front, artwork, albumart usw.
- Alle Tracks eines Albums werden nach eingebetteten Covern durchsucht.
- Vorschau zählt dadurch deutlich realistischer.


## Änderungen in v1.9.35

- Eingebettete Cover aus Mp3tag werden robuster erkannt.
- MP3/APIC, ältere PIC-Frames, direkte ID3-Erkennung und generischer Mutagen-Fallback ergänzt.
- Diagnose-Endpunkt `/api/covers/detection_stats` ergänzt.


## Änderungen in v1.9.35

- Cover-Vorschau/Job gruppiert bevorzugt nach MusicLab-Albumdaten aus der DB statt rein nach Ordnern.
- Dadurch sollten Werte näher an der MusicLab-Albumzahl liegen.
- Export `Cover-Fehlerliste exportieren` ergänzt, um angeblich fehlende Cover zu prüfen.


## Änderungen in v1.9.35

- Cover-Vorschau/Job gruppiert jetzt wie die Medien-/Albumansicht primär nach Albumname.
- Sampler werden dadurch nicht mehr pro Track-Künstler als einzelne coverlose Alben gezählt.
- Cover-Erkennung nutzt zusätzlich `_embedded_cover_from_file()`, also die gleiche bewährte Funktion wie sichtbare MusicLab-Cover.
