# MusicLab v1.9.18 Synology Project Safe

Diese Version ist bewusst für deinen gewohnten Synology-Ablauf gebaut:

```text
Projekt stoppen → bereinigen → neu erstellen
```

## Wichtigste Änderung

Das Frontend wird nicht mehr fest in ein eigenes Docker-Image kopiert, sondern per Bind-Mount aus dem NAS-Ordner geladen:

```yaml
/volume1/docker/musiclab/frontend:/usr/share/nginx/html:ro
/volume1/docker/musiclab/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro
```

Das Backend-App-Verzeichnis wird ebenfalls gemountet:

```yaml
/volume1/docker/musiclab/backend/app:/app/app:ro
```

Dadurch verwendet der Container nach dem Neu-Erstellen direkt die Dateien, die du nach `/volume1/docker/musiclab` kopiert hast. Synology kann dadurch nicht mehr still ein altes Frontend-Image weiterverwenden.

## Enthalten

```text
docker-compose.yml
install_musiclab_ssh.sh
frontend/
backend/
data/
README.md
CREDITS.md
```

## Nicht mehr enthalten

```text
docker-compose.dev-volumes.example.yml
docker-compose.override.yml
update_musiclab.sh
__pycache__/
*.pyc
.DS_Store
```

## Installation

ZIP direkt nach `/volume1/docker/musiclab` entpacken/kopieren.

Empfohlen: `data/` nicht löschen, sonst geht die Datenbank mit Analysewerten verloren.

Danach entweder wie gewohnt im Synology Container Manager:

```text
Projekt stoppen → bereinigen → neu erstellen
```

oder per SSH:

```bash
cd /volume1/docker/musiclab
chmod +x install_musiclab_ssh.sh
./install_musiclab_ssh.sh
```

Danach öffnen:

```text
http://192.168.188.34:8092/?v=1913
```


## Hinweis zu data/

`data/.keep` ist enthalten, damit der Ordner sicher mit in der ZIP landet. Eine vorhandene `data/musiclab.sqlite` auf der NAS nicht löschen, wenn Analysewerte erhalten bleiben sollen.


## Änderungen in v1.9.18

- Batch-Button `Ausführen` bleibt nach Auswahl einer Aktion aktiv und wird nicht mehr vom Status-Poller grundlos ausgegraut.
- Dropdown `Aktion wählen…` aktualisiert den Button sofort per `onchange`.
- Die Arbeitsfläche unter den Tabs skaliert dynamisch anhand der echten Header-Höhe.
- Synology-Projektmodus bleibt erhalten.


## Änderungen in v1.9.18

- Backend-Fehler `name 'normalize_parallelism' is not defined` vollständig behoben.
- Alter Aufruf `normalize_parallelism()` bekommt einen Kompatibilitätswrapper.
- Parallelität wird aus `parallel_normalize` gelesen und auf sichere Werte begrenzt.
