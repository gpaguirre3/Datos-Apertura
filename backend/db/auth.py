import os
import secrets
import time
from pathlib import Path

from flask import request
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, registros

CARPETA = Path(__file__).resolve().parents[1]  
# En Docker se apunta a un volumen para que las sesiones sobrevivan al redespliegue
CLAVE_SECRETA = Path(os.environ.get("CLAVE_SESION_ARCHIVO") or CARPETA / ".clave_sesion")
INTENTOS_MAX, BLOQUEO_SEG = 5, 5 * 60
CLAVE_MINIMA = 4
ADMIN_INICIAL = ("admin", "admin123")
SESION_POR_DEFECTO = 300 

fallidos = {}  


def minutos_sesion():
    try:
        return max(1, int(os.environ.get("SESION_MINUTOS") or SESION_POR_DEFECTO))
    except ValueError:
        return SESION_POR_DEFECTO


def ip_cliente():
    """IP real de quien se conecta"""
    reenviada = request.headers.get("X-Forwarded-For", "")
    return (reenviada.split(",")[0].strip() if reenviada else request.remote_addr) or "?"

def cifrar(clave):
    return generate_password_hash(clave)

def problema_clave(clave):
    if len(clave) < CLAVE_MINIMA:
        return f"La contraseña debe tener al menos {CLAVE_MINIMA} caracteres."
    if clave == ADMIN_INICIAL[1]:
        return "No uses la contraseña inicial."
    return None

def preparar_base():
    db.crear_tablas()
    db.migrar_json(CARPETA / "usuarios.json")
    if not db.contar_usuarios():
        db.crear_usuario(ADMIN_INICIAL[0], cifrar(ADMIN_INICIAL[1]), "admin")
        registros.registrar_cambio("sistema", None, "crear_usuario", ADMIN_INICIAL[0], "administrador inicial")


def verificar(usuario, clave):
    ahora = time.time()
    intentos, hasta = fallidos.get(usuario, (0, 0))
    if hasta > ahora:
        return f"Demasiados intentos. Espera {int((hasta - ahora) // 60) + 1} minuto(s).", "BLOQUEADO"
    datos = db.obtener_usuario(usuario)
    if not datos or not check_password_hash(datos["hash"], clave):
        intentos += 1
        fallidos[usuario] = (0, ahora + BLOQUEO_SEG) if intentos >= INTENTOS_MAX else (intentos, 0)
        return "Usuario o contraseña incorrectos.", "FALLIDO"
    fallidos.pop(usuario, None)
    return None, "OK"


def registrar(accion, objetivo=None, detalle=None, usuario=None):
    registros.registrar_cambio(usuario or "?", ip_cliente(), accion, objetivo, detalle)


def fecha_texto(valor):
    return valor.strftime("%Y-%m-%d %H:%M:%S") if hasattr(valor, "hour") else (valor.isoformat() if valor else None)


def configurar(app):
    """Al arrancar: crea la clave con la que se firman los tokens y deja la base lista."""
    if not CLAVE_SECRETA.exists():
        CLAVE_SECRETA.parent.mkdir(parents=True, exist_ok=True)
        CLAVE_SECRETA.write_text(secrets.token_hex(32))
        try:
            CLAVE_SECRETA.chmod(0o600)
        except OSError:
            pass
    preparar_base()
