# Arquitectura

## Visión general

```
Navegador
   │
   ▼
Caddy ─── /api/* ──► Flask (gunicorn)
   │                    │
   └── resto ──► nginx  ├─► Playwright / Chromium ──► páginas públicas
                 Angular├─► MySQL
                        └─► PyMuPDF (arma los PDF)
```

El frontend es una aplicación Angular servida como archivos estáticos. No comparte
nada con el backend salvo la API REST y la cookie de sesión.

El backend es un único proceso de Flask. **Esto importa**: los trabajos en curso
viven en un diccionario en memoria, así que no se puede escalar a varios workers sin
mover ese estado a la base o a Redis.

## Carpetas del backend

| Carpeta | Responsabilidad |
|---|---|
| `controlador/` | la API REST: rutas, sesión, CSRF y permisos |
| `procesos/` | el catálogo de consultas y el ciclo de vida de los trabajos |
| `descargas/` | un robot por fuente, más el consolidado y la portada |
| `documentos/` | utilidades sobre PDF y Excel |
| `db/` | conexión, esquema, autenticación y registros de auditoría |

La dependencia va siempre en el mismo sentido: `controlador` → `procesos` →
`descargas` / `documentos` → `db`. Ningún robot conoce Flask.

## El flujo de un trabajo

1. El navegador sube el Excel a `POST /api/procesos/vista-previa` y recibe un
   resumen: cuántas filas hay, cuántas cédulas distintas y una muestra.
2. Confirma con `POST /api/procesos`, que valida permisos y archivo, crea un
   identificador y lanza un hilo.
3. El hilo recorre las cédulas en lotes de 10 y va escribiendo el avance en el
   diccionario `trabajos`.
4. El navegador consulta `GET /api/procesos/<id>/estado` cada 2 segundos.
5. Al terminar, `GET /api/procesos/<id>/zip` comprime la carpeta y la entrega.

Los trabajos caducan a las 2 horas y una tarea los borra del disco.

### Cancelación

Cada trabajo lleva un `threading.Event`. Los robots lo consultan entre cédula y
cédula, así que una cancelación se atiende al terminar la consulta en curso, no al
instante.

## Cómo se arma el PDF

`descargas/consolidado.py` es el orquestador. Cada robot deja su resultado en
`partes/<fuente>/<cédula>.<ext>`, y luego, por cada cédula, se monta un PDF con este
orden fijo:

1. **Portada** — Mina, Aduana y Procesos judiciales, las tres capturas compuestas en
   una hoja A4 por PyMuPDF.
2. **SUPA**
3. **ISSPOL**
4. **ISSFA**

Terminado el PDF de cada persona, `partes/` se borra. La entrega queda así:

```
consolidado_todos.pdf    todos los PDF concatenados
individuales.zip         un PDF por cédula
resultado.csv            estado y detalle de cada consulta
```

## Estado y persistencia

| Qué | Dónde | Sobrevive al reinicio |
|---|---|---|
| Usuarios y sesión activa | MySQL | sí |
| Clave que firma los JWT | archivo (`CLAVE_SESION_ARCHIVO`) | sí, si está en un volumen |
| Registros de auditoría | JSON en `logs/` | sí |
| Trabajos en curso | memoria del proceso | **no** |
| Archivos de los trabajos | disco (`storage/temp/`) | sí, pero quedan huérfanos |

Reiniciar el backend con trabajos corriendo los pierde: no hay reanudación.

## Frontend

Angular 20 con componentes standalone y señales; sin NgRx ni RxJS más allá de HTTP.

- `core/` — servicios de sesión, interceptores y guardas
- `features/procesos/` — subir el Excel, ver el avance, descargar
- `features/administrar/` — usuarios, solo para el rol `admin`
- `layout/` — barra lateral y cabecera
- `shared/ui/` — componentes reutilizables

Un interceptor añade `withCredentials` y la cabecera CSRF. Un servicio comprueba la
sesión cada segundo, de modo que si alguien entra desde otro equipo, aquí se cierra
en menos de un segundo.
