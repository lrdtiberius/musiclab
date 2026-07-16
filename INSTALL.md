# Installation MusicLab v2.2.0

## Synology
1. Projekt stoppen.
2. `/volume1/docker/musiclab/data` sichern.
3. ZIP entpacken und Dateien nach `/volume1/docker/musiclab` kopieren.
4. Vorhandenen `data`-Ordner behalten.
5. Musikpfad in `docker-compose.yml` prüfen.
6. Projekt bereinigen und neu erstellen.
7. Auf gesunden Backend-Status warten.
8. `http://NAS-IP:8092` öffnen.

## SSH
```bash
cd /volume1/docker/musiclab
chmod +x install_musiclab_ssh.sh
./install_musiclab_ssh.sh
```

## Ports
- Frontend: 8092
- Backend: 8091
