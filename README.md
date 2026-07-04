# MusicLab v0.7.2

Fix-Release nach v0.7.1.

## Änderungen
- Frontend-JavaScript-Fehler behoben, wodurch Buttons wie „Bibliothek neu scannen“ nicht reagierten.
- Analyse-Parser robuster gemacht: ffmpeg-Ausgaben mit zusätzlichen `{...}`-Blöcken oder Backslashes verursachen nicht mehr sofort `Invalid \\escape`.
- Version auf v0.7.2 angehoben.

## Update
1. ZIP-Inhalt nach `/volume1/docker/musiclab` kopieren.
2. Container/Projekt neu starten.
3. Browser hart neu laden: `Cmd + Shift + R`.

Bei aktivem Volume-Mount für `frontend/index.html` und `backend/app` reicht meistens ein Neustart der Container.
