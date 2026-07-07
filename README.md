# MusicLab v1.8.0

MusicLab – lokale Musikbibliothek analysieren, normalisieren, taggen und prüfen.

## Neu in v1.8.0

- Neuer Tab **Bibliotheksprüfung**
  - echte Duplikate innerhalb desselben Albums
  - mehrfach vorhandene Titel als Hinweis, nicht als Fehler
  - Dateikonflikte nach Sortierung
  - fehlende Jahre, Genres, Cover und beschädigte/fehlende Dateien
- Protokoll-Autoscroll repariert: manuelles Hochscrollen springt nicht mehr nach unten.
- Nach Normalisierung bleibt der Auto-Refresh aktiv.
- Credits/Projektidentität ergänzt:
  - `CREDITS.md`
  - `NOTICE`
  - Backend-Endpunkt `/api/about`

## Projektstruktur

```text
backend/
frontend/
data/
docker-compose.yml
README.md
LICENSE
NOTICE
CREDITS.md
```

## Credit

MusicLab – Idea & Umsetzung by Lrd.Tiberius.
Copyright © 2026 Lrd.Tiberius.
