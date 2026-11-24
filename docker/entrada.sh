#!/usr/bin/env bash
# Levanta la pantalla virtual y su visor web, y luego la API.
set -euo pipefail

TAMANO="${PANTALLA_TAMANO:-1920x1080x24}"
export DISPLAY="${DISPLAY:-:99}"

Xvfb "$DISPLAY" -screen 0 "$TAMANO" -nolisten tcp &

for _ in $(seq 1 50); do
    xdpyinfo -display "$DISPLAY" >/dev/null 2>&1 && break
    sleep 0.2
done
xdpyinfo -display "$DISPLAY" >/dev/null 2>&1 || { echo "No arrancó la pantalla virtual" >&2; exit 1; }

# Solo escucha dentro del contenedor: quien entra pasa antes por Caddy
x11vnc -display "$DISPLAY" -forever -shared -nopw -localhost -rfbport 5900 -quiet &
websockify --web=/usr/share/novnc 6080 localhost:5900 &

exec gunicorn --bind 0.0.0.0:4200 --workers 1 --threads 8 --timeout 600 \
     --access-logfile - app:app
