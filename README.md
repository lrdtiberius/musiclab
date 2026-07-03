# MusicLab v0.2.1

Stabilisierungs-Patch für die Bibliotheksanzeige.

## Änderungen

- Anzeige von Tracknummern korrigiert: `1/0` wird als `1` angezeigt.
- `1/12` bleibt weiterhin `1/12`.
- UI-Version auf v0.2.1 aktualisiert.
- Schema-Version angehoben, damit die Datenbank beim Rebuild sauber neu aufgebaut wird.

## Installation auf Synology

1. Inhalt dieser ZIP nach `/volume1/docker/musiclab` kopieren.
2. Container Manager: Projekt stoppen.
3. Bereinigen.
4. Falls DSM cached: alte Images löschen.
5. Projekt neu erstellen/starten.
6. Browser hart neu laden: `Cmd + Shift + R`.
7. Bibliothek neu scannen.
