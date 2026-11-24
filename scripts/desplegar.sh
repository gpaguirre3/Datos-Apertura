#!/usr/bin/env bash
# Construye y levanta todo. Uso: ./scripts/desplegar.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f config/produccion.env ]]; then
    echo "Falta config/produccion.env. Cópialo de config/produccion.env.ejemplo y rellénalo." >&2
    exit 1
fi

mkdir -p logs storage/temp backups database/inicio
docker compose build
docker compose up -d
docker compose ps
echo "Listo. Revisa los registros con: docker compose logs -f backend"
