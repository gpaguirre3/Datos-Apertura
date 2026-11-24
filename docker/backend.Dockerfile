# API y robots. Trae Chromium y sus librerías ya instaladas.
FROM mcr.microsoft.com/playwright/python:v1.65.0-noble

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Pantalla virtual y visor web, para marcar el captcha de Procesos judiciales
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb x11-utils x11vnc novnc websockify \
    && ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn \
    && playwright install chromium

COPY backend/ .
COPY docker/entrada.sh /usr/local/bin/entrada.sh

ENV DISPLAY=:99 PANTALLA_REMOTA=si
# Un solo proceso de gunicorn: los trabajos viven en memoria y se comparten entre hilos
CMD ["/usr/local/bin/entrada.sh"]
