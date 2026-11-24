# Apertura de Datos

Consulta masiva de registros públicos ecuatorianos a partir de un listado de cédulas
en Excel. Se sube el archivo, la aplicación consulta cada fuente, arma un PDF por
persona y entrega todo en un ZIP.

## Qué hace

De un `.xlsx` con cédulas saca, según la opción elegida:

| Consulta | Fuente |
|---|---|
| ISSPOL | Policía Nacional |
| ISSFA | Fuerzas Armadas |
| SUPA | Pensiones alimenticias |
| Portada | Mina, Aduana y Procesos judiciales en una hoja |
| Consolidado | las cuatro anteriores en un solo PDF por cédula |

Más utilidades sobre archivos: unir PDF, extraer la primera hoja, cédula a nombre,
datos de familia y montos a letras.

El resultado es un ZIP con el PDF consolidado de todos, un `individuales.zip` con
el PDF de cada cédula y un `resultado.csv` que dice qué se obtuvo y qué falló.

## Cómo está construido

- **Backend**: Python 3.13 y Flask. Los robots son Playwright sobre Chromium.
- **Frontend**: Angular 20, componentes standalone y señales.
- **Base**: MySQL 8.
- **Producción**: Docker Compose, con Caddy delante.

## Arrancarlo en tu equipo

Necesitas Python 3.11+, Node 20+ y MySQL.

```bash
# Base de datos (las tablas se crean solas en el primer arranque)
mysql -u root -p -e "CREATE DATABASE sacardatos CHARACTER SET utf8mb4;"

# Backend
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.ejemplo .env        # y rellena DB_* y MINA_*
python app.py               # queda en http://127.0.0.1:4200

# Frontend, en otra terminal
cd frontend
npm install
npm start                   # queda en http://localhost:4201
```

Entra en `http://localhost:4201` con **`admin` / `admin123`** y cambia esa
contraseña de inmediato.

## Estructura

```
backend/        API Flask y robots de consulta
frontend/       Angular
docker/         Dockerfiles, Caddyfile, nginx.conf y entrada.sh
config/         configuración de producción (produccion.env)
scripts/        desplegar.sh y respaldo.sh
database/       SQL de inicialización
docs/           documentación técnica
logs/           registros de auditoría (generado)
storage/        trabajos en curso y entregas (generado)
backups/        volcados de la base (generado)
```

## Documentación

| Documento | Para qué |
|---|---|
| [docs/arquitectura.md](docs/arquitectura.md) | cómo encajan las piezas y qué hace cada carpeta |
| [docs/api.md](docs/api.md) | endpoints, autenticación y formatos |
| [docs/consultas.md](docs/consultas.md) | el catálogo y cómo funciona cada robot |
| [docs/desarrollo.md](docs/desarrollo.md) | entorno local, convenciones y tareas comunes |
| [docs/seguridad.md](docs/seguridad.md) | sesiones, roles, secretos y qué vigilar |
| [docs/despliegue.md](docs/despliegue.md) | puesta en producción con Docker |

## Limitaciones conocidas

**Procesos judiciales exige un captcha** resuelto por una persona. En el servidor se
hace a través de la pantalla remota (ver `docs/despliegue.md`); sin ella, esa consulta
y las que la incluyen salen incompletas.

**Las páginas consultadas son ajenas.** Cambian de maquetación sin avisar y a veces
bloquean al servidor por su origen o su ritmo. Cuando una consulta falla en todas las
cédulas, lo primero a mirar es la propia página.
