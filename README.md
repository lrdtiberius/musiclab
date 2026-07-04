# MusicLab v0.9.3

Neu in v0.9.3:

- Parallel-Analyse für einzelne Alben, Alles analysieren und Batch-Analyse.
- Einstellbare Parallelität im UI: 1, 2, 3, 4 oder 6 parallele ffmpeg-Prozesse.
- Standard bleibt konservativ auf 2, damit die DS923+ nicht unnötig überlastet wird.
- Stop-Button zum Abbrechen laufender Jobs.
- Scan, Analyse, Batch-Analyse, Normalisierung und Batch-Normalisierung reagieren auf den Stop-Befehl.
- Laufende ffmpeg-Prozesse werden nicht hart gekillt; der Abbruch erfolgt sauber nach dem aktuellen Titel bzw. nach den aktuell laufenden Analyse-Jobs.
- Backend-Version 0.9.3, DB-Schema 10.
- data/ ist enthalten.

Hinweis zur Parallelität:

Für die DS923+ empfehle ich zunächst 2 oder 3. Bei 4 kann es deutlich schneller werden, erzeugt aber mehr CPU- und Festplattenlast. 6 ist nur zum Testen gedacht.
