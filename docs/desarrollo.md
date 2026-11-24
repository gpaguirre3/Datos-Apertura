# Desarrollo

## Montar el entorno

Requisitos: Python 3.11+, Node 20+ y MySQL.

```bash
mysql -u root -p -e "CREATE DATABASE sacardatos CHARACTER SET utf8mb4;"

cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.ejemplo .env
python app.py
```

```bash
cd frontend
npm install
npm start
```

El backend queda en el 4200 y el frontend en el 4201. `proxy.conf.json` manda `/api`
al backend, así que en desarrollo no hay CORS.

El primer arranque crea las tablas y el usuario `admin` / `admin123`.

## Convenciones

**El código se escribe en español**: nombres de funciones, variables y comentarios.
Es deliberado, por el equipo que lo mantiene. Las palabras del lenguaje y de las
librerías quedan en inglés, naturalmente.

**Comentarios, los justos.** Se comenta el porqué, no el qué. Si una línea necesita
explicar lo que hace, casi siempre es mejor reescribirla.

**Angular**: componentes standalone, señales en lugar de RxJS para el estado,
`input()` y `output()` en vez de decoradores. Plantilla y estilos en archivos
aparte, nunca en línea.

**Flask**: la lógica no vive en las rutas. Una ruta valida, delega y responde.

## Tareas comunes

### Añadir una consulta

Ver [consultas.md](consultas.md). Resumen: escribir el robot en `descargas/` y
añadirlo a `CATALOGO` y `MODULOS`. El frontend no se toca.

### Probar un robot suelto

```bash
cd backend
python -m descargas.descargar_supa cedulas.xlsx --salida prueba --visible
```

`--visible` abre el navegador para ver qué pasa. Lo aceptan todos menos el de
Procesos judiciales, que siempre lo abre.

### Cambiar la duración de la sesión

`SESION_MINUTOS` en el `.env`. Son minutos; por omisión 300, o sea 5 horas.

### Mirar los registros de auditoría

Son JSON planos en `backend/registros/` (en producción, `logs/`):

```bash
python -c "import json;print(*json.load(open('registros/accesos.json'))[-10:],sep='\n')"
```

## Qué romper con cuidado

**Un solo proceso.** Los trabajos viven en memoria. Si algún día se arranca con
varios workers de gunicorn, el navegador puede preguntar por un trabajo a un proceso
que no lo tiene. Antes habría que mover ese estado fuera.

**Las cookies.** El token va en una cookie `HttpOnly` y las peticiones que modifican
algo exigen la cabecera `X-CSRF-Token`. Si se cambia una parte, hay que cambiar las
dos: el interceptor del frontend y el decorador del backend.

**La sesión única.** El campo `sid` del token se compara contra la columna `sesion`
del usuario. Tocar uno sin el otro cierra sesiones que deberían seguir vivas.

**El tamaño de ventana de Aduana.** Es fijo a propósito. Adaptarlo a la pantalla hace
que el PNG cambie de ancho según el equipo, y con él la portada.

## Compilar para producción

```bash
cd frontend
npm run build -- --base-href /Apertura/
```

El `base-href` tiene que coincidir con la subcarpeta donde se publique, y
`environment.prod.ts` debe apuntar a `<subcarpeta>/api`. Si se sirve en la raíz,
ambos valores pierden el prefijo. Es un error fácil de cometer y se manifiesta como
una pantalla en blanco.
