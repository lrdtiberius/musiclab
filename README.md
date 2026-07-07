# MusicLab v1.8.12

## Änderungen

- Sortierung nach Tags repariert: MusicLab lässt veraltete `Album Artist`-Tags nicht mehr die sichtbare Interpret-Korrektur zurückdrehen.
- Beispiel: `Die Arzte` wird nicht mehr wiederhergestellt, wenn der sichtbare Artist bereits `Die Ärzte` ist.
- Beim Speichern von Tags schreibt das Feld `Interpret` jetzt sowohl `artist` als auch `albumartist`.
- Die Duplikatseite bleibt ohne Pfad-Öffnen/Pfad-Kopieren-Buttons; Pfade werden nur noch angezeigt.
- Version/Cache-Buster auf 1.8.12 gesetzt.

## Nach dem Update

```bash
docker compose down
docker compose up -d --build
```

Danach den Browser hart neu laden.

## Hinweis

Falls alte Dateien bereits unterschiedliche Werte für `artist` und `albumartist` enthalten, korrigiere den Interpret einmal in MusicLab und speichere. Ab dieser Version werden beide Felder synchron geschrieben.
