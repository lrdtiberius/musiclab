#!/bin/sh
set -e

cd "$(dirname "$0")"

echo "== MusicLab v1.9.11 Update / Rebuild =="
echo "Arbeitsordner: $(pwd)"
echo

echo "== Prüfe NAS-Musikpfad =="
if [ ! -d /volume1/DS420/Musik ]; then
  echo "WARNUNG: /volume1/DS420/Musik wurde auf der NAS nicht gefunden."
else
  echo "OK: /volume1/DS420/Musik vorhanden"
  ls -lah /volume1/DS420/Musik | head
fi
echo

echo "== Versionen in den Quelldateien =="
grep -R "MusicLab v" -n frontend/index.html || true
grep -R "APP_VERSION" -n frontend/app.js | head || true
grep -R "APP_VERSION" -n backend/app/main.py | head || true
echo

echo "== Compose-Konfiguration =="
sudo docker compose config | grep -A35 -B8 "musiclab-backend" || true
sudo docker compose config | grep -A25 -B5 "musiclab-frontend" || true
echo

echo "== Alte MusicLab-Container entfernen =="
sudo docker rm -f musiclab-frontend musiclab-backend 2>/dev/null || true
echo

echo "== Alte MusicLab-Images entfernen =="
sudo docker image rm musiclab-musiclab-frontend musiclab-musiclab-backend 2>/dev/null || true
echo

echo "== Ohne Cache neu bauen =="
sudo docker compose build --no-cache
echo

echo "== Neu starten =="
sudo docker compose up -d --force-recreate
echo

echo "== Frontend prüfen =="
sudo docker exec musiclab-frontend ls -lah /usr/share/nginx/html
sudo docker exec musiclab-frontend grep -R "MusicLab v" -n /usr/share/nginx/html/index.html || true
curl -s http://localhost:8092 | grep -i "MusicLab v" || true
echo

echo "== Backend prüfen =="
sudo docker exec musiclab-backend python - <<'PY'
from app.main import APP_VERSION, check_music_root, get_music_root, get_settings
print("Backend APP_VERSION:", APP_VERSION)
print("Backend music_root:", get_music_root())
print("Backend settings:", get_settings())
print("Backend check_music_root:", check_music_root(str(get_music_root())))
PY
echo

echo "== Backend HTTP Pfadcheck =="
curl -s "http://localhost:8091/api/settings/check_music_root?path=/music" || true
echo
curl -s "http://localhost:8091/api/version" || true
echo

echo "Fertig. Browser-Adresse: http://192.168.188.34:8092"
