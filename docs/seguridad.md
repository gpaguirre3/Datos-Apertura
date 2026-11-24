# Seguridad

## Sesiones

El token es un JWT firmado con HS256 y viaja en una cookie `HttpOnly`,
`SameSite=Strict`, y `Secure` cuando la conexión es HTTPS. Al ser `HttpOnly`, el
JavaScript de la página no puede leerlo: un XSS no se lleva la sesión.

Contra CSRF se usa doble testigo: una segunda cookie legible y la cabecera
`X-CSRF-Token`, que el servidor compara con `secrets.compare_digest`. Se exige en
todo método que modifique datos.

**Una sesión por usuario.** Entrar desde otro equipo cierra la anterior en menos de
un segundo. Impide compartir una cuenta entre varias personas, que es lo que
convierte la auditoría en papel mojado.

Tras 5 intentos fallidos la cuenta se bloquea 5 minutos.

## Contraseñas

Se guardan cifradas con scrypt (`werkzeug.security`). En claro no quedan en ningún
sitio: ni en la base, ni en los registros, ni en memoria más allá de la comprobación.

El mínimo son 4 caracteres y no puede usarse la inicial. Es un mínimo bajo,
adecuado a una aplicación de red interna; si algún día se publica en internet,
`CLAVE_MINIMA` en `db/auth.py` es lo primero que hay que subir.

**El usuario `admin` / `admin123` se crea solo en el primer arranque.** Cambiarlo es
el primer paso de cualquier instalación.

## Roles

Dos: `admin` y `usuario`.

Solo `admin` administra usuarios y ve las consultas marcadas `solo_admin` (Mina
Nombres, Montos a letras y Primera hoja). El filtro se aplica **en el servidor**, en
`catalogo_publico()` y otra vez al lanzar: ocultar un botón no es un permiso.

## Secretos

| Secreto | Dónde vive | Nunca debe |
|---|---|---|
| Contraseña de la base | `config/produccion.env` | subirse al repositorio |
| Credenciales de Mina | `config/produccion.env` | aparecer en los registros |
| Clave que firma los JWT | archivo, en un volumen | perderse o filtrarse |

`config/produccion.env`, `backend/.env` y `.clave_sesion` están en el `.gitignore`.
Antes de cada commit vale la pena comprobar que siguen fuera.

La clave de firma se genera sola en el primer arranque, con 32 bytes aleatorios. Si
se pierde, todas las sesiones caen y hay que volver a entrar; si se filtra, cualquiera
puede fabricar tokens válidos. Por eso en Docker vive en un volumen y no dentro de
la imagen.

## Qué vigilar en producción

**La pantalla remota del captcha.** Quien entra a `/pantalla/` maneja un navegador
dentro del servidor y puede navegar a donde quiera desde su IP. Tiene dos barreras,
y conviene entender por qué son dos:

- La **página** del visor exige sesión abierta en la app: Caddy se lo pregunta a la
  propia API con `forward_auth`.
- El **websocket** (`/websockify`) no pasa por esa comprobación, porque `forward_auth`
  impide completar la negociación del protocolo. Ahí la protección es `VISOR_CLAVE`,
  la contraseña del propio VNC.

Sin `VISOR_CLAVE` definida, cualquiera de la red que conozca la dirección del
websocket ve y maneja ese navegador. El arranque lo avisa en los registros, pero no
lo impide: defínela siempre. El límite son 8 caracteres, impuesto por el protocolo
VNC, así que no es una contraseña fuerte — es una barrera razonable en red interna,
no en internet.

La página la pueden abrir todos los usuarios, no solo los administradores. Si eso no
encaja con tu operación, hay que apuntar el `forward_auth` a un endpoint que además
compruebe el rol.

**La base expuesta.** Si MySQL corre fuera de Docker, `bind-address = 0.0.0.0` lo
deja escuchando en toda la red. Conviene restringir el usuario a las direcciones de
Docker y cerrar el 3306 en el cortafuegos.

**Red interna sin HTTPS.** Servida por HTTP, las contraseñas viajan en claro por la
red local. La aplicación lo detecta y ajusta la cookie para que funcione, pero el
tráfico sigue sin cifrar. Que sea una decisión tomada, no un descuido.

## Auditoría

En `logs/` quedan los accesos —con usuario, IP, agente y resultado— y las acciones
relevantes: crear y editar usuarios, lanzar y cancelar trabajos, descargar ZIP.

Son archivos JSON con tope de 20 000 líneas. La escritura usa un candado y reemplazo
atómico, así que se pueden leer en caliente sin riesgo de verlos a medio escribir.

## Datos personales

La aplicación maneja cédulas y nombres de personas reales, y los PDF que genera
contienen información sensible de terceros.

Los trabajos se borran del disco a las 2 horas y el ZIP se elimina al descargarse,
una sola vez. Aun así, `storage/temp/` contiene datos personales mientras los
trabajos están vivos: debe tratarse con el mismo cuidado que la base, y los
respaldos de `backups/` no deberían salir del servidor sin cifrar.
