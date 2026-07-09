# MusicLab v1.9.8 Fixed Full

Diese ZIP ist eine bereinigte Komplettversion.

Wichtig:
- Inhalt der ZIP direkt nach `/volume1/docker/musiclab` entpacken.
- Vorhandene Dateien ersetzen.
- `docker-compose.yml` enthält keine Frontend-/Backend-Code-Bind-Mounts mehr.
- `frontend/Dockerfile` kopiert `index.html`, `app.js`, `styles.css`, `assets/` und `nginx.conf` ins Nginx-Image.

## Update auf der NAS

```bash
cd /volume1/docker/musiclab
chmod +x update_musiclab.sh
./update_musiclab.sh
```

Danach öffnen:

```text
http://192.168.188.34:8092
```

Nicht nur `http://192.168.188.34`.

## Manuelle Prüfung

```bash
sudo docker exec musiclab-frontend ls -lah /usr/share/nginx/html
sudo docker exec musiclab-frontend grep -R "MusicLab v" -n /usr/share/nginx/html/index.html
curl -s http://localhost:8092 | grep -i "MusicLab v"
```

Erwartet: `MusicLab v1.9.8`.
