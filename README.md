# MusicLab v1.1.5

Musikbibliothek scannen, LUFS/True-Peak/LRA analysieren und Alben oder Titel normalisieren.

## Projektstruktur

```text
MusicLab/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       └── main.py
├── frontend/
│   ├── Dockerfile
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   └── assets/
├── data/
│   ├── backups/
│   └── logs/
├── docker-compose.yml
├── README.md
└── LICENSE
```

## Synology-Installation

1. Den kompletten Ordner nach `/volume1/docker/musiclab` kopieren.
2. Im Container Manager ein neues Projekt aus diesem Ordner erstellen.
3. Projekt starten.
4. Oberfläche öffnen: `http://<NAS-IP>:8092`
5. Backend API: `http://<NAS-IP>:8091/api/status`

## Hinweise

- Der Ordner `data/` ist absichtlich enthalten und wird für Datenbank, Logs und Backups genutzt.
- Frontend-Dateien liegen jetzt sauber getrennt in `frontend/index.html`, `frontend/app.js` und `frontend/styles.css`.
- macOS-Metadatenordner wie `__MACOSX` und `._*` sind nicht enthalten.

Idea by Lrd.Tiberius.
