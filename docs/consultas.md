# Consultas y robots

## El catálogo

Está en `procesos/catalogo.py`, en la lista `CATALOGO`. Es la única fuente de verdad:
el frontend dibuja sus pantallas a partir de lo que devuelve `GET /api/catalogo`.

### Pantalla «Consultas»

| Clave | Nombre | Qué hace |
|---|---|---|
| `isspol` | ISSPOL | certificado de la Policía Nacional |
| `issfa` | ISSFA | certificado de Fuerzas Armadas |
| `supa` | SUPA | tarjetas de pensiones alimenticias |
| `portada` | PORTADA | Mina, Aduana y Procesos judiciales en una hoja |
| `consolidado` | Consolidado | las cuatro anteriores, un PDF por cédula |

### Pantalla «Obtener datos»

| Clave | Nombre | Solo admin |
|---|---|---|
| `mina_nombres` | Mina Nombres (cédula → nombre) | sí |
| `mina_familia` | Datos para Solicitar Dato Seguro | no |
| `montos` | Montos a letras | sí |
| `unir_pdf` | Unir PDF | no |
| `primera_hoja` | Primera hoja de un PDF | sí |
| `unir_cedula` | Aperturas con Dato Seguro | no |

### Añadir una consulta

1. Escribe el robot en `descargas/`, con una función
   `procesar(cedulas, salida, al_avanzar=None, cancelado=None)`.
2. Añade la entrada al `CATALOGO` y el módulo al diccionario `MODULOS`.

No hay que tocar el frontend: la opción aparece sola.

Banderas disponibles en una entrada: `solo_admin` restringe al rol `admin`,
`requiere_mina` la desactiva si falta `MINA_AUTORIZADO=si`, `segundo_archivo` pide
otro archivo y `ordenes` ofrece alternativas de orden.

## Cómo es un robot por dentro

Todos siguen la misma forma, con Playwright sobre Chromium:

```python
def procesar(cedulas, salida, visible=False, espera=60, al_avanzar=None, cancelado=None):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, proxy=leer_proxy())
        page = browser.new_page(...)

        def intentar(cedula):
            ...
            return "OK", "detalle"      # o ("ERROR", motivo)

        return con_reintentos(cedulas, lambda c: c, intentar, salida, al_avanzar,
                              cancelado=cancelado)
```

`con_reintentos`, en `descargar_certificados.py`, recorre las cédulas, informa del
avance y vuelve a intentar al final las que fallaron (2 intentos extra). Ese módulo
también concentra lo compartido: leer el Excel, el proxy, las capturas de error,
`ajustar_ventana` y `centrar_captcha`.

Las URL de todas las fuentes salen del `.env`, no están escritas en el código.

## Fuentes, una por una

| Robot | Ventana | Entrega |
|---|---|---|
| `descargar_certificados.py` (ISSPOL) | oculta | PDF |
| `descargar_issfa.py` | oculta | PDF |
| `descargar_supa.py` | oculta | PDF impreso de la página |
| `descargar_aduana.py` | pantalla virtual | PNG recortado |
| `descargar_mina.py` | oculta | PNG recortado |
| `descargar_judicial.py` | **visible, con captcha** | PNG recortado |

Aduana necesita ventana real, así que levanta un Xvfb propio si no hay pantalla, y
manda la ventana fuera del monitor para no estorbar. Su tamaño es fijo a propósito:
así la captura sale idéntica en cualquier equipo.

### Procesos judiciales y su captcha

Es el único que exige una persona. Por eso:

- Abre la ventana **visible** y la maximiza con `ajustar_ventana`, que se adapta a
  cualquier pantalla, de 640×480 a 4K.
- Si aparece el reto de imágenes, `centrar_captcha` lo coloca en el centro y lo
  encoge si no cabe. Sin eso, Google lo ancla junto a la casilla y queda cortado.
- Espera hasta 180 segundos (`ESPERA_CAPTCHA`). Pasados, esa cédula se marca y el
  lote continúa.
- Deja 15 segundos entre búsquedas (`JUDICIAL_PAUSA`) para no parecer un bot,
  que es lo que dispara el reto de imágenes en vez de la simple casilla.
- Usa un **perfil de navegador persistente** (`JUDICIAL_PERFIL`): las cookies de Google
  sobreviven entre ejecuciones. Un navegador sin historia es lo que más hace que
  reCAPTCHA rechace respuestas correctas y encadene rondas. Si dos consultas de
  Procesos judiciales coinciden, la segunda usa un perfil temporal, porque Chromium
  no deja abrir el mismo perfil dos veces.

### Si el captcha rechaza respuestas correctas

reCAPTCHA no puntúa solo los clics: puntúa el navegador entero. Si lo considera
sospechoso, sigue pidiendo rondas aunque se acierte. Lo que ayuda, de más a menos:

1. **Iniciar sesión con una cuenta de Google** en ese navegador, una vez, desde la
   pantalla remota. Con el perfil persistente la sesión se mantiene, y es lo que más
   rebaja la dificultad.
2. Subir `JUDICIAL_PAUSA` (30-60 s) si se lanzan muchas cédulas seguidas.
3. En los retos de «haz clic hasta que no quede ninguna», las imágenes se reponen:
   hay que esperar a que terminen de aparecer y seguir marcando hasta que no salga
   ninguna más antes de pulsar Verificar.

En el servidor el aviso cambia solo: con `PANTALLA_REMOTA` definida, en vez de decir
«marca la casilla en la ventana» indica abrir la pantalla remota.

## Ritmo y tolerancia a fallos

| Constante | Dónde | Valor |
|---|---|---|
| `LOTE` | `consolidado.py` | 10 cédulas por vuelta |
| `REINTENTOS` | `descargar_certificados.py` | 2 intentos extra |
| `PAUSA_ENTRE_CONSULTAS` | `descargar_judicial.py` | 15 s |
| `ESPERA_CAPTCHA` | `descargar_judicial.py` | 180 s |
| `VIDA_TRABAJO` | `procesos/catalogo.py` | 2 horas |

Si una fuente se cae del todo, se marca como no disponible y las demás siguen: no se
aborta el trabajo entero. Esa cédula queda como `INCOMPLETO` y el motivo se escribe
en `resultado.csv`.

## Cuando una página cambia

Es lo que más mantenimiento da, y es inevitable: son sitios ajenos.

Señal típica: **todas** las cédulas fallan con el mismo error. En `storage/temp/`
quedan capturas del momento del fallo; suele bastar con mirarlas para ver si cambió
un selector, si pide un captcha nuevo o si el sitio está caído.

Para depurar en local, los robots aceptan `visible=True` y se pueden ejecutar sueltos:

```bash
python -m descargas.descargar_supa cedulas.xlsx --salida prueba --visible
```
