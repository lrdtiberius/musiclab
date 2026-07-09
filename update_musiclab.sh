#!/bin/sh
set -e

cd "$(dirname "$0")"

echo "== MusicLab Update / Rebuild =="
echo "Arbeitsordner: $(pwd)"
echo

echo "== Prüfe wichtige Dateien =="
ls -lah docker-compose.yml frontend/Dockerfile frontend/index.html frontend/app.js frontend/styles.css frontend/nginx.conf
echo

echo "== Version in frontend/index.html =="
grep -R "MusicLab v" -n frontend/index.html || true
echo

echo "== Docker Compose config: Frontend darf KEIN volumes: nach /usr/share/nginx/html haben =="
sudo docker compose config | grep -A25 -B5 "musiclab-frontend" || true
echo

echo "== Container stoppen =="
sudo docker compose down --remove-orphans
echo

echo "== Images ohne Cache neu bauen =="
sudo docker compose build --no-cache
echo

echo "== Container neu starten =="
sudo docker compose up -d --force-recreate
echo

echo "== Container-Dateien prüfen =="
sudo docker exec musiclab-frontend ls -lah /usr/share/nginx/html
echo

echo "== Version im laufenden Container =="
sudo docker exec musiclab-frontend grep -R "MusicLab v" -n /usr/share/nginx/html/index.html || true
echo

echo "== HTTP-Test Port 8092 =="
curl -s http://localhost:8092 | grep -i "MusicLab v" || true
echo

echo "Fertig. Im Browser öffnen: http://192.168.188.34:8092"
