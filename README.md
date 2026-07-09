# MusicLab v1.9.11 Flat Install

Diese ZIP ist absichtlich **flach** gebaut. Beim Entpacken direkt nach:

```text
/volume1/docker/musiclab
```

müssen direkt diese Dateien/Ordner dort liegen:

```text
docker-compose.yml
install_musiclab_ssh.sh
frontend/
backend/
data/
```

Nicht in einem Unterordner.

## Installation

```bash
cd /volume1/docker/musiclab
chmod +x install_musiclab_ssh.sh
./install_musiclab_ssh.sh
```

Danach öffnen:

```text
http://192.168.188.34:8092
```

Erwartet: MusicLab v1.9.11.
