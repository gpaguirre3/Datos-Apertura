# API

Todas las rutas cuelgan de `/api`. Las respuestas son JSON, salvo la descarga del ZIP.
Un error siempre llega como `{"error": "texto para mostrar al usuario"}`.

## Autenticación

El token es un JWT firmado con HS256. **No se devuelve en el cuerpo**: viaja en una
cookie `HttpOnly`, de modo que el JavaScript de la página no puede leerlo y un XSS no
se lo puede llevar.

| Cookie | Contenido | Legible por JS |
|---|---|---|
| `sacardatos_sesion` | el JWT | no |
| `sacardatos_csrf` | testigo contra CSRF | sí |

Ambas van con `SameSite=Strict`, y con `Secure` cuando la petición llega por HTTPS.

En los métodos que modifican algo (`POST`, `PUT`, `DELETE`) hay que enviar la cabecera
`X-CSRF-Token` con el valor de la cookie `sacardatos_csrf`. El servidor compara ambos
valores; si no coinciden, responde **403** con `{"error": "CSRF"}`.

Cada petición válida renueva la cookie, así que la sesión se mantiene mientras se
use. La duración sale de `SESION_MINUTOS` (300 por omisión).

### Una sola sesión por usuario

Al entrar se genera un identificador nuevo y se guarda en la columna `sesion` del
usuario. El token lleva ese identificador en el campo `sid`. Si alguien entra desde
otro equipo, el identificador cambia y el token anterior deja de valer: la respuesta
pasa a ser **401** con `{"error": "SESION_REEMPLAZADA"}`, y el frontend lo detecta en
menos de un segundo.

## Sesión

### `POST /auth/login`

```json
{ "usuario": "admin", "clave": "..." }
```

Devuelve los datos del usuario y pone las dos cookies. Tras 5 intentos fallidos la
cuenta queda bloqueada 5 minutos.

### `GET /auth/me`

Datos del usuario y segundos que le quedan a la sesión. No la renueva, así que sirve
de latido sin alargarla indefinidamente.

### `POST /auth/logout`

Borra la sesión en la base y las cookies. El token anterior ya no vale.

## Catálogo

### `GET /catalogo`

Lista de consultas disponibles **para ese usuario**: las marcadas `solo_admin` no
aparecen si el rol no es `admin`. Cada entrada trae:

| Campo | Significado |
|---|---|
| `clave` | identificador interno |
| `nombre`, `detalle` | lo que se muestra |
| `pagina` | en qué pantalla se agrupa |
| `extension` | qué archivo pide (`.xlsx` o `.zip`) |
| `segundo_archivo` | si necesita un segundo archivo |
| `ordenes` | opciones de orden, cuando las tiene |
| `disponible`, `motivo` | falso si falta `MINA_AUTORIZADO=si` |

## Procesos

### `POST /procesos/vista-previa`

`multipart/form-data` con `clave`, `archivo` y, si procede, `archivo2`.

Devuelve qué se leyó del archivo antes de lanzar nada: total de filas, cédulas
distintas, columnas y una muestra con el número de repeticiones de cada una. Si el
Excel trae una columna de nombres, también se incluyen.

### `POST /procesos`

Los mismos campos, más `orden` cuando la consulta lo admite. Devuelve
`{"id": "...", "total": N}`.

Errores posibles: **400** si el archivo no corresponde o falta permiso, **403** si la
consulta es solo para administradores.

### `GET /procesos/<id>/estado`

```json
{
  "total": 120,
  "fin": false,
  "filas": [["0101010101", "OK", "4 consultas"], ["0202020202", "CAPTCHA", "..."]]
}
```

Estados que puede tomar una fila: `EN PROCESO`, `EN ESPERA`, `CAPTCHA`,
`REINTENTANDO`, `OK`, `OMITIDO`, `INCOMPLETO`, `ERROR`, `CANCELADO`.

`CAPTCHA` es el único que exige intervención: alguien debe marcar la casilla.

Responde **404** si el trabajo caducó, a las 2 horas.

### `POST /procesos/<id>/cancelar`

Pide la cancelación. Se atiende al terminar la cédula en curso, no de inmediato.

### `GET /procesos/<id>/zip`

Devuelve el ZIP y **borra el trabajo**: solo se puede descargar una vez.

## Administración

Solo para el rol `admin`.

| Ruta | Qué hace |
|---|---|
| `GET /admin/usuarios` | lista de usuarios |
| `POST /admin/usuarios` | crea uno (`usuario`, `clave`, `rol`) |
| `POST /admin/usuarios/<usuario>` | edita nombre, rol o contraseña |

La contraseña exige 4 caracteres como mínimo y no puede ser la inicial. Se guarda
cifrada con scrypt; en claro no se almacena en ningún sitio.

## Auditoría

Accesos y acciones se registran en archivos JSON dentro de `logs/`, con un tope de
20 000 líneas por archivo. La escritura está protegida con un candado y se hace de
forma atómica, así que se puede leer el archivo mientras la aplicación trabaja.
