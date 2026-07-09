#!/bin/sh
set -e
cd "$(dirname "$0")"

echo "== Source frontend files =="
ls -lah frontend
echo

echo "== Source frontend version =="
grep -R "MusicLab v" -n frontend/index.html || true
echo

echo "== frontend/Dockerfile =="
cat frontend/Dockerfile
echo

echo "== Rebuild frontend without cache =="
sudo docker compose down --remove-orphans
sudo docker compose build --no-cache musiclab-frontend
sudo docker compose up -d --force-recreate
echo

echo "== Container HTML files =="
sudo docker exec musiclab-frontend ls -lah /usr/share/nginx/html
echo

echo "== Container version =="
sudo docker exec musiclab-frontend grep -R "MusicLab v" -n /usr/share/nginx/html/index.html || true
echo

echo "== Direct HTTP check =="
curl -s http://localhost:8092 | grep -i "MusicLab v" || true
