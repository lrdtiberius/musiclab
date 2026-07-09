# MusicLab v1.8.28

## Neu in v1.8.28

- Einzelauswahl-Markierung repariert: Beim Wechsel von Interpret oder Album wird die vorherige optische Markierung automatisch entfernt.
- Schnellere Klickwechsel abgesichert: Späte Antworten alter Auswahl-Ladevorgänge überschreiben die aktuelle Auswahl nicht mehr.

- Geschwindigkeit der Normalisierung verbessert.
- Neue Einstellung **Parallel-Normalisierung** mit 1–4 parallelen ffmpeg-Jobs.
- Standard bleibt vorsichtig bei 2×.
- Normalisierung verwendet vorhandene Analysewerte wieder, statt vor jedem Titel erneut eine komplette Loudness-Vormessung zu starten.
- Dadurch spart MusicLab pro Datei einen ffmpeg-Durchlauf, wenn die Titel bereits analysiert sind.
- Kopfzeile zeigt nun getrennt **Analyse ×** und **Norm ×**.

## Empfehlung

Für eine Synology/NAS-Umgebung:

- Analyse: 2–4×
- Normalisierung: 2× sicher, 3× testen, 4× nur wenn NAS/Volume nicht einbricht
- Backup eingeschaltet lassen

Nach dem Update bitte neu bauen:

```bash
docker compose down
docker compose up -d --build
```

Danach den Browser hart neu laden.
