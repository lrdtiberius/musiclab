#!/bin/sh
set -e
cd "$(dirname "$0")"

echo "== Quelle prüfen =="
pwd
grep -R "MusicLab v" -n frontend/index.html || true
grep -R "APP_VERSION" -n backend/app/main.py | head || true
echo

echo "== Compose prüfen: KEIN /usr/share/nginx/html und KEIN /app/app =="
sudo docker compose config | grep -A35 -B8 "musiclab-backend" || true
sudo docker compose config | grep -A25 -B5 "musiclab-frontend" || true
echo

echo "== MusicLab Container entfernen =="
sudo docker rm -f musiclab-frontend musiclab-backend 2>/dev/null || true
echo

echo "== MusicLab Images entfernen =="
sudo docker image rm musiclab-musiclab-frontend musiclab-musiclab-backend 2>/dev/null || true
sudo docker image rm musiclab-frontend musiclab-backend 2>/dev/null || true
echo

echo "== Ohne Cache neu bauen =="
sudo docker compose build --no-cache --pull
echo

echo "== Neu starten =="
sudo docker compose up -d --force-recreate
echo

echo "== Frontend im Container =="
sudo docker exec musiclab-frontend ls -lah /usr/share/nginx/html
sudo docker exec musiclab-frontend grep -R "MusicLab v" -n /usr/share/nginx/html/index.html || true
curl -s http://localhost:8092 | grep -i "MusicLab v" || true
echo

echo "== Backend im Container =="
sudo docker exec musiclab-backend python - <<'PY'
from app.main import APP_VERSION, get_music_root, check_music_root
print("APP_VERSION:", APP_VERSION)
print("music_root:", get_music_root())
print("check:", check_music_root(str(get_music_root())))
PY
curl -s http://localhost:8091/api/version || true
echo
curl -s "http://localhost:8091/api/settings/check_music_root?path=/music" || true
echo

echo "== Backend Mounts =="
sudo docker inspect musiclab-backend --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
echo

echo "Fertig. Öffnen: http://192.168.188.34:8092"
