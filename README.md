# MusicLab v0.4.3

Fix:
- JavaScript-Fehler im Log-Block behoben (`lines.join('\n')`)
- Button „Bibliothek neu scannen“ startet wieder zuverlässig
- Fehler beim Starten von Scan/Analyse werden im Log-Bereich angezeigt
- Version auf v0.4.3 angehoben

Installation:
1. Inhalt nach `/volume1/docker/musiclab` kopieren.
2. Projekt stoppen.
3. Container neu starten.
4. Browser hart neu laden: `Cmd + Shift + R`.

Wichtig:
Die `docker-compose.yml` sollte weiterhin `frontend/index.html` und `backend/app` als Volume mounten, damit Änderungen sofort greifen.
