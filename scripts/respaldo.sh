#!/usr/bin/env bash
# Vuelca la base en backups/. Uso: ./scripts/respaldo.sh
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source config/produccion.env; set +a

mkdir -p backups
destino="backups/sacardatos_$(date +%Y%m%d_%H%M).sql.gz"
docker compose exec -T db mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" \
    --single-transaction "$MYSQL_DATABASE" | gzip > "$destino"
echo "Respaldo en $destino"

# Conserva los últimos 14
ls -1t backups/sacardatos_*.sql.gz | tail -n +15 | xargs -r rm --
