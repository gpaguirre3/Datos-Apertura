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

## Publicar bajo una subcarpeta

Por omisión la app se sirve en la raíz del dominio. Para publicarla en
`http://servidor/Apertura` hay **cuatro** sitios que deben coincidir, porque la ruta
queda grabada en el build de Angular:

| Archivo | Qué lleva |
|---|---|
| `docker/frontend.Dockerfile` | `npm run build -- --base-href /Apertura/` |
| `frontend/src/environments/environment.prod.ts` | `apiUrl: '/Apertura/api'` |
| `docker/Caddyfile` | las rutas `/Apertura/api/*`, `/Apertura/pantalla/*` y `/Apertura/*` |
| `tabla-avance.html` | el enlace a `/Apertura/pantalla/` |

Cambiar solo el Caddyfile da una pantalla en blanco: el navegador pide los archivos
en la raíz y no los encuentra. Tras cualquier cambio hay que reconstruir el frontend:

```bash
docker compose up -d --build frontend caddy
```

## Si ya hay otro servidor web en el puerto 80

Es frecuente: otro Apache, nginx o Caddy ocupando el 80 y el 443. Dos salidas.

**Publicar en otro puerto.** Lo menos intrusivo:

```yaml
    ports: ["8080:80"]
```

y se entra por `http://servidor:8080`.

**Ponerlo detrás del servidor que ya existe.** Se publica solo en local
(`ports: ["127.0.0.1:8080:80"]`), se pone `DOMINIO=:80` para que Caddy acepte
cualquier nombre de host, y el servidor de delante reenvía. Con Apache:

```apache
ProxyPass        /Apertura/pantalla/websockify ws://127.0.0.1:8080/Apertura/pantalla/websockify
ProxyPassReverse /Apertura/pantalla/websockify ws://127.0.0.1:8080/Apertura/pantalla/websockify
ProxyPass        /Apertura http://127.0.0.1:8080/Apertura
ProxyPassReverse /Apertura http://127.0.0.1:8080/Apertura
```

La regla del `websockify` va **antes** que la general, o la pantalla remota no
funciona: se aplica la primera que encaja. Requiere `a2enmod proxy proxy_http
proxy_wstunnel`.

## Base de datos fuera de Docker

Si MySQL ya existe en el servidor, se quita el servicio `db` del compose, se borra
el volumen `datos_mysql` y en el servicio `backend` se añade:

```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

En `config/produccion.env`, `DB_HOST=host.docker.internal`. Y en MySQL,
`bind-address = 0.0.0.0` en `/etc/mysql/mysql.conf.d/mysqld.cnf`, seguido de
`systemctl restart mysql`: un contenedor no alcanza el `127.0.0.1` del servidor.

Eso deja la base escuchando en toda la red, así que conviene restringir el usuario
a las direcciones de Docker y cerrar el puerto:

```sql
RENAME USER 'sacardatos'@'%' TO 'sacardatos'@'172.%';
```

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
