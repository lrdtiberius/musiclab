# Optional / nicht nötig für Synology-Projektmodus.
# Das Frontend wird in docker-compose.yml direkt per nginx:alpine gestartet
# und aus /volume1/docker/musiclab/frontend gemountet.
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY app.js /usr/share/nginx/html/app.js
COPY styles.css /usr/share/nginx/html/styles.css
COPY assets /usr/share/nginx/html/assets
RUN chmod -R 755 /usr/share/nginx/html
