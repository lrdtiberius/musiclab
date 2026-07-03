# MusicLab v0.1

Erste lauffähige Version: Musikbibliothek scannen, Interpreten/Alben/Titel anzeigen.

## Installation Synology

1. Ordner nach `/volume1/docker/musiclab` kopieren.
2. Im Container Manager neues Projekt aus diesem Ordner erstellen.
3. Starten.
4. Frontend öffnen: `http://NAS-IP:8092`
5. Backend API: `http://NAS-IP:8091/api/health`

## Wichtig

Musikpfad in `docker-compose.yml`:

```yaml
- /volume1/DS420/Musik:/music
```

Falls dein Pfad anders ist, anpassen.
