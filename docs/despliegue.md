# Despliegue en producción (Docker)

## Qué levanta

| Servicio   | Imagen               | Para qué |
|------------|----------------------|----------|
| `caddy`    | caddy:2              | HTTPS y reparto: `/api/*` al backend, el resto al frontend |
| `frontend` | nginx + Angular      | La interfaz ya compilada |
| `backend`  | Playwright + Python  | La API y los robots, con gunicorn |
| `db`       | mysql:8.4            | La base de datos |

## Puesta en marcha

```bash
cp config/produccion.env.ejemplo config/produccion.env
nano config/produccion.env          # dominio, contraseñas y credenciales de Mina
./scripts/desplegar.sh
```

El dominio debe apuntar ya al servidor y los puertos 80 y 443 estar libres: Caddy
saca el certificado solo en el primer arranque.

**Solo en red interna**, sin dominio público, se pone la IP con prefijo:
`DOMINIO=http://192.168.1.50`. Caddy sirve en claro por el puerto 80 y no intenta
sacar certificado. La app detecta que no hay HTTPS y ajusta la cookie de sesión,
así que funciona igual; lo que no hay es cifrado dentro de la red.

La primera vez el backend crea las tablas y el usuario `admin` con clave `admin123`.
**Cámbiala nada más entrar.**

## Qué se guarda y dónde

| Ruta | Contenido |
|------|-----------|
| `logs/` | registros de auditoría en JSON |
| `storage/temp/` | trabajos en curso y zips de entrega |
| `backups/` | volcados de la base (`./scripts/respaldo.sh`) |
| volumen `datos_mysql` | los datos de MySQL |
| volumen `secretos` | la clave que firma las sesiones |

El volumen `secretos` importa: si se pierde, todas las sesiones abiertas se caen
y hay que volver a entrar.

## El captcha de Procesos judiciales

Esa consulta exige que una persona marque "No soy un robot". Para que se pueda hacer
desde el servidor, el contenedor del backend levanta una pantalla virtual (Xvfb) y la
publica por web con noVNC.

Cuando una consulta llega al captcha:

1. En la tabla de avance aparece el estado `CAPTCHA` y un botón **Abrir pantalla remota**.
2. Se abre `https://TU_DOMINIO/pantalla/`, que muestra el navegador del servidor.
3. Se marca la casilla, o se resuelve el reto de imágenes, y el proceso sigue solo.

Hay 3 minutos para hacerlo; pasados, esa cédula queda marcada y el lote continúa.

**Quién puede entrar ahí.** Caddy no deja pasar a `/pantalla/` sin una sesión abierta
en la app: por cada petición le pregunta a la propia API. Aun así, ten presente que
quien entra maneja un navegador dentro de tu servidor, así que trátalo como un acceso
sensible y no lo compartas fuera del equipo.

El visor solo escucha dentro del contenedor; no hay ningún puerto VNC expuesto al
exterior. El tamaño de la pantalla se cambia con `PANTALLA_TAMANO` en
`config/produccion.env`.

## Operación diaria

```bash
docker compose logs -f backend     # ver qué está pasando
docker compose restart backend     # reiniciar solo la API
./scripts/respaldo.sh              # volcado de la base a backups/
docker compose down                # parar todo (los datos se conservan)
```

## Actualizar

```bash
git pull            # o copia los archivos nuevos
./scripts/desplegar.sh
```

Reconstruye las imágenes y reemplaza los contenedores. La base, los registros y la
clave de sesión se conservan.

## Si algo falla

**No carga la página o el certificado no sale.** `docker compose logs caddy`.
Casi siempre es el DNS todavía sin propagar o el puerto 80 ocupado por otro servicio.

**Dice usuario o contraseña incorrectos sin serlo.** Suele ser la base: mira
`docker compose logs backend`. Comprueba que `DB_PASSWORD` y `MYSQL_PASSWORD`
tengan el mismo valor en `config/produccion.env`.

**No deja iniciar sesión aunque la clave sea buena.** Entra siempre por la misma
dirección que pusiste en `DOMINIO`. Si la app se sirve por HTTPS pero entras por
`http://`, o al revés, la cookie de sesión no viaja.

**Un robot falla en todas las cédulas.** Normalmente es la página de origen caída
o bloqueando al servidor. En `storage/temp/` quedan capturas del error.
