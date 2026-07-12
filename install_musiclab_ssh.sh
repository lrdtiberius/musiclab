#!/bin/sh
set -e
cd "$(dirname "$0")"

echo "== MusicLab v2.0.0-beta1 Synology-Projektmodus =="
echo "Quelle: $(pwd)"
grep -R "MusicLab v" -n frontend/index.html || true
grep -R "APP_VERSION" -n frontend/app.js | head || true
grep -R "APP_VERSION" -n backend/app/main.py | head || true
echo

echo "== Compose prüfen =="
sudo docker compose config | grep -A45 -B8 "musiclab-backend" || true
sudo docker compose config | grep -A35 -B5 "musiclab-frontend" || true
echo

echo "== Projekt neu starten =="
sudo docker compose down --remove-orphans
sudo docker compose up -d --build --force-recreate
echo

echo "== Frontend prüfen =="
sudo docker exec musiclab-frontend grep -R "MusicLab v" -n /usr/share/nginx/html/index.html || true
curl -s http://localhost:8092 | grep -i "MusicLab v" || true
echo

echo "== Backend prüfen =="
sudo docker exec musiclab-backend grep -R "APP_VERSION" -n /app/app/main.py | head || true
curl -s http://localhost:8091/api/version || true
echo
curl -s "http://localhost:8091/api/settings/check_music_root?path=/music" || true
echo

echo "== Mounts =="
sudo docker inspect musiclab-frontend --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}' || true
sudo docker inspect musiclab-backend --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}' || true
echo

echo "Fertig. Öffnen: http://192.168.188.34:8092/?v=1939"
