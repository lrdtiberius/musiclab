# MusicLab v0.6.0

Neu in v0.6.0:

- Albumsuche innerhalb des ausgewählten Interpreten.
- Albumliste bleibt scrollbar und zeigt Trefferanzahl.
- Auswahl bleibt stabil, auch während Status-Polling läuft.
- Buttons werden während laufender Jobs sauber deaktiviert.
- Backend-API `/api/albums` unterstützt jetzt `q=` als Filter.
- Analyse-Logging bereinigt.

Installation:

1. ZIP-Inhalt nach `/volume1/docker/musiclab` kopieren.
2. Projekt im Container Manager stoppen.
3. Projekt neu starten. Durch die Volume-Mounts sind Frontend/Backend-Dateien sofort aktiv.
4. Browser hart neu laden: `Cmd + Shift + R`.

Hinweis: Bestehende Datenbank kann weiterverwendet werden.
