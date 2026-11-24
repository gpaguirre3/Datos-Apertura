#!/usr/bin/env bash
# Levanta la pantalla virtual y su visor web, y luego la API.
set -euo pipefail

TAMANO="${PANTALLA_TAMANO:-1920x1080x24}"
export DISPLAY="${DISPLAY:-:99}"

# Al reiniciarse el contenedor queda el bloqueo de la ejecución anterior
NUMERO="${DISPLAY#:}"
rm -f "/tmp/.X${NUMERO}-lock" "/tmp/.X11-unix/X${NUMERO}" 2>/dev/null || true

Xvfb "$DISPLAY" -screen 0 "$TAMANO" -nolisten tcp &

for _ in $(seq 1 50); do
    xdpyinfo -display "$DISPLAY" >/dev/null 2>&1 && break
    sleep 0.2
done
# Sin pantalla la API debe seguir: solo se pierde el captcha de Procesos judiciales
xdpyinfo -display "$DISPLAY" >/dev/null 2>&1 \
    || echo "AVISO: no arrancó la pantalla virtual; Procesos judiciales no estará disponible" >&2

# Contraseña del visor: sin ella cualquiera de la red vería esta pantalla
if [ -n "${VISOR_CLAVE:-}" ]; then
    mkdir -p /root/.vnc
    x11vnc -storepasswd "$VISOR_CLAVE" /root/.vnc/passwd >/dev/null 2>&1
    AUTENTICACION="-rfbauth /root/.vnc/passwd"
else
    echo "AVISO: VISOR_CLAVE sin definir; la pantalla remota queda sin contraseña" >&2
    AUTENTICACION="-nopw"
fi

# Solo escucha dentro del contenedor: se llega por Caddy
x11vnc -display "$DISPLAY" -forever -shared $AUTENTICACION -localhost -rfbport 5900 -quiet &
websockify --web=/usr/share/novnc 6080 localhost:5900 &

exec gunicorn --bind 0.0.0.0:4200 --workers 1 --threads 8 --timeout 600 \
     --access-logfile - app:app
