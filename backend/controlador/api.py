
import os
import re
import secrets
import time
import uuid
from functools import wraps

import jwt
from flask import Blueprint, g, jsonify, make_response, request, send_file

import procesos
from db import auth, db, registros

api = Blueprint("api", __name__, url_prefix="/api")

ALGORITMO = "HS256"
MARGEN_SEG = 30

# El token va en una cookie que el navegador no deja leer a JavaScript: así un
# XSS no puede robarlo. Como la cookie se manda sola en cada petición, hace
# falta comprobar aparte que la petición salga de la propia aplicación: eso es
# COOKIE_CSRF, que sí es legible y debe repetirse en la cabecera CABECERA_CSRF.
COOKIE_SESION = "sacardatos_sesion"
COOKIE_CSRF = "sacardatos_csrf"
CABECERA_CSRF = "X-CSRF-Token"
METODOS_SEGUROS = ("GET", "HEAD", "OPTIONS")


def _clave():
    return auth.CLAVE_SECRETA.read_text().strip()


def _emitir(usuario, rol, sesion):
    ahora = int(time.time())
    carga = {"sub": usuario, "rol": rol, "sid": sesion, "iat": ahora,
             "exp": ahora + auth.minutos_sesion() * 60 + MARGEN_SEG}
    return jwt.encode(carga, _clave(), algorithm=ALGORITMO)


def _leer_token():
    token = request.cookies.get(COOKIE_SESION)
    if not token:
        return None
    try:
        return jwt.decode(token, _clave(), algorithms=[ALGORITMO])
    except jwt.PyJWTError:
        return None


def _seguro():
    """True si la conexión llega por https, también detrás de un proxy."""
    return request.headers.get("X-Forwarded-Proto", request.scheme) == "https"


def _poner_cookies(respuesta, token, csrf=None):
    """Deja la sesión en la respuesta. La del token no la ve JavaScript; la de
    CSRF sí, porque el front tiene que devolverla en la cabecera."""
    objeto = make_response(respuesta)
    duracion = auth.minutos_sesion() * 60 + MARGEN_SEG
    objeto.set_cookie(COOKIE_SESION, token, max_age=duracion, httponly=True,
                      samesite="Strict", secure=_seguro(), path="/")
    if csrf:
        objeto.set_cookie(COOKIE_CSRF, csrf, max_age=duracion, httponly=False,
                          samesite="Strict", secure=_seguro(), path="/")
    return objeto


def _usuario_publico(datos, restante_seg):
    return {"usuario": datos["usuario"], "rol": datos["rol"],
            "restante": restante_seg}


def sin_renovar(f):
    f._no_renueva = True
    return f


def con_sesion(f):
    """Exige un token válido y un usuario que siga pudiendo entrar."""
    @wraps(f)
    def envoltura(*args, **kwargs):
        carga = _leer_token()
        if not carga:
            return jsonify(error="La sesión terminó. Vuelve a iniciar sesión.", codigo="SIN_SESION"), 401
        datos = db.obtener_usuario(carga.get("sub", ""))
        if not datos:
            return jsonify(error="La sesión terminó. Vuelve a iniciar sesión.", codigo="SIN_SESION"), 401
        # Solo vale la última sesión abierta: entrar en otro equipo cierra esta,
        if carga.get("sid") != datos["sesion"]:
            return jsonify(error="Tu sesión se cerró porque se entró desde otro equipo.",
                           codigo="SESION_REEMPLAZADA"), 401
        # Lo que cambia algo debe venir de la propia aplicación, no de otra web
        # que aproveche que la cookie viaja sola.
        if request.method not in METODOS_SEGUROS:
            enviado = request.headers.get(CABECERA_CSRF, "")
            guardado = request.cookies.get(COOKIE_CSRF, "")
            if not guardado or not secrets.compare_digest(enviado, guardado):
                return jsonify(error="Solicitud no válida.", codigo="CSRF"), 403
        g.usuario = datos
        respuesta = f(*args, **kwargs)
        if getattr(f, "_no_renueva", False) or g.get("no_renovar", False):
            return respuesta
        return _poner_cookies(respuesta, _emitir(datos["usuario"], datos["rol"], carga.get("sid")))
    return envoltura


def solo_admin(f):
    @wraps(f)
    def envoltura(*args, **kwargs):
        if g.usuario["rol"] != "admin":
            return jsonify(error="Solo para administradores.", codigo="SIN_PERMISO"), 403
        return f(*args, **kwargs)
    return envoltura


def registrar(accion, objetivo=None, detalle=None):
    """Auditoría con el usuario del token, no con la cookie."""
    auth.registrar(accion, objetivo, detalle, usuario=g.usuario["usuario"])


# --- Sesión ---


@api.post("/auth/login")
def login():
    cuerpo = request.get_json(silent=True) or {}
    usuario = str(cuerpo.get("usuario", "")).strip().lower()
    mensaje, resultado = auth.verificar(usuario, str(cuerpo.get("clave", "")))
    registros.registrar_acceso(usuario or "(vacío)", auth.ip_cliente(),
                               request.headers.get("User-Agent"), resultado)
    if mensaje:
        return jsonify(error=mensaje), 401
    datos = db.obtener_usuario(usuario)
    # Identificador nuevo en cada entrada: invalida la sesión que hubiera abierta.
    sesion = uuid.uuid4().hex
    db.guardar_sesion(usuario, sesion)
    return _poner_cookies(jsonify(**_usuario_publico(datos, auth.minutos_sesion() * 60)),
                          _emitir(usuario, datos["rol"], sesion), csrf=secrets.token_hex(16))


@api.get("/auth/me")
@con_sesion
@sin_renovar
def me():
    carga = _leer_token() or {}
    restante = max(0, int(carga.get("exp", 0) - time.time() - MARGEN_SEG))
    return jsonify(**_usuario_publico(g.usuario, restante))


@api.post("/auth/logout")
@con_sesion
@sin_renovar
def logout():
    db.guardar_sesion(g.usuario["usuario"], None)
    registrar("cerrar_sesion", g.usuario["usuario"])
    objeto = make_response(jsonify(ok=True))
    for cookie in (COOKIE_SESION, COOKIE_CSRF):
        objeto.delete_cookie(cookie, path="/", samesite="Strict", secure=_seguro())
    return objeto


# --- Procesos ---


@api.get("/catalogo")
@con_sesion
def catalogo():
    """Qué procesos hay, con sus reglas: el front no duplica esas condiciones."""
    return jsonify(procesos=procesos.catalogo_publico(g.usuario["rol"] == "admin"))


@api.post("/procesos/vista-previa")
@con_sesion
def vista_previa():
    try:
        return jsonify(**procesos.previsualizar(request.form.get("sitio", ""),
                                                request.files.get("excel"),
                                                request.files.get("zip2"),
                                                es_admin=g.usuario["rol"] == "admin"))
    except procesos.ErrorProceso as e:
        return jsonify(error=str(e)), 400


@api.post("/procesos")
@con_sesion
def lanzar_proceso():
    try:
        tid, nombre, cuantos = procesos.lanzar(
            request.form.get("sitio", ""),
            request.files.get("excel"),
            archivo2=request.files.get("zip2"),
            orden=request.form.get("orden", "consolidado"),
            usuario=g.usuario["usuario"],
            es_admin=g.usuario["rol"] == "admin",
        )
    except procesos.ErrorProceso as e:
        return jsonify(error=str(e)), 400
    nombre_archivo = (request.files.get("excel").filename or "")
    registrar("lanzar_proceso", nombre, f"{cuantos} registro(s), archivo {nombre_archivo}, trabajo {tid}")
    return jsonify(id=tid, nombre=nombre, total=cuantos)


@api.get("/procesos/<tid>/estado")
@con_sesion
def estado_proceso(tid):
    datos = procesos.estado(tid)
    if datos is None:
        g.no_renovar = True
        return jsonify(error="Ese trabajo ya no existe."), 404
    g.no_renovar = datos["fin"]
    return jsonify(**datos)


@api.post("/procesos/<tid>/cancelar")
@con_sesion
def cancelar_proceso(tid):
    nombre = procesos.cancelar(tid)
    if nombre is None:
        return jsonify(error="Ese trabajo ya no existe."), 404
    registrar("cancelar_proceso", nombre, f"trabajo {tid}")
    return jsonify(ok=True)


@api.get("/procesos/<tid>/zip")
@con_sesion
def descargar_zip(tid):
    resultado = procesos.comprimir(tid, borrar=True)
    if resultado is None:
        return jsonify(error="Ese trabajo no dejó archivos."), 404
    ruta, nombre = resultado
    registrar("descargar_zip", nombre, f"trabajo {tid}")
    respuesta = send_file(ruta, mimetype="application/zip", as_attachment=True,
                          download_name=nombre)
    respuesta.call_on_close(lambda: ruta.unlink(missing_ok=True))
    return respuesta


# --- Administración ---

def _fecha(valor):
    return auth.fecha_texto(valor)

def _lista_usuarios():
    accesos = registros.ultimo_acceso_por_usuario()
    return [
        {"usuario": u["usuario"], "rol": u["rol"],
         "creado": _fecha(u["creado"]), "actualizado": _fecha(u["actualizado"]),
         "ultimo_acceso": accesos.get(u["usuario"])}
        for u in db.listar_usuarios()
    ]


def _respuesta_usuarios():
    return jsonify(usuarios=_lista_usuarios(), yo=g.usuario["usuario"])


def _error(mensaje):
    return jsonify(error=mensaje), 400


@api.get("/admin/usuarios")
@con_sesion
@solo_admin
def admin_usuarios():
    return _respuesta_usuarios()


@api.post("/admin/usuarios")
@con_sesion
@solo_admin
def admin_crear_usuario():
    d = request.get_json(silent=True) or {}
    usuario = str(d.get("usuario", "")).strip().lower()
    clave = str(d.get("clave", ""))
    if not re.fullmatch(r"[a-z0-9._-]{3,30}", usuario):
        return _error("El usuario debe tener de 3 a 30 letras, números, punto, guion o guion bajo.")
    if db.obtener_usuario(usuario):
        return _error("Ese usuario ya existe.")
    problema = auth.problema_clave(clave)
    if problema:
        return _error(problema)
    rol = "admin" if d.get("rol") == "admin" else "usuario"
    db.crear_usuario(usuario, auth.cifrar(clave), rol)
    registrar("crear_usuario", usuario, f"rol {rol}")
    return _respuesta_usuarios()


@api.post("/admin/usuarios/<usuario>")
@con_sesion
@solo_admin
def admin_editar_usuario(usuario):
    d = request.get_json(silent=True) or {}
    datos = db.obtener_usuario(usuario)
    if not datos:
        return _error("Ese usuario no existe.")
    accion = d.get("accion")
    yo = g.usuario["usuario"]

    if accion == "nombre":
        nuevo = str(d.get("nombre", "")).strip().lower()
        if not re.fullmatch(r"[a-z0-9._-]{3,30}", nuevo):
            return _error("Usuario de 3 a 30 caracteres: letras, números, punto, guion o guion bajo.")
        if nuevo != usuario:
            if db.obtener_usuario(nuevo):
                return _error(f"El usuario {nuevo} ya existe.")
            db.renombrar_usuario(usuario, nuevo)
            registrar("renombrar_usuario", usuario, f"ahora se llama {nuevo}")
            if usuario == yo:
                g.usuario["usuario"] = nuevo

    elif accion == "clave":
        clave = str(d.get("clave", ""))
        problema = auth.problema_clave(clave)
        if problema:
            return _error(problema)
        db.actualizar_usuario(usuario, hash=auth.cifrar(clave))
        registrar("cambiar_clave", usuario)

    elif accion == "rol":
        rol = "admin" if d.get("rol") == "admin" else "usuario"
        if rol == "usuario" and db.administradores() == [usuario]:
            return _error("Debe quedar al menos un administrador.")
        db.actualizar_usuario(usuario, rol=rol)
        registrar("cambiar_rol", usuario, f"{datos['rol']} → {rol}")

    elif accion == "eliminar":
        if usuario == yo:
            return _error("No puedes eliminar tu propio usuario.")
        if db.administradores() == [usuario]:
            return _error("Debe quedar al menos un administrador.")
        db.eliminar_usuario(usuario)
        registrar("eliminar_usuario", usuario, f"rol {datos['rol']}")

    else:
        return _error("Acción no válida.")
    return _respuesta_usuarios()
