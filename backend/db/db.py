import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pymysql

ECUADOR = timezone(timedelta(hours=-5))

TABLAS = [
    """CREATE TABLE IF NOT EXISTS usuarios (
        id INT AUTO_INCREMENT PRIMARY KEY,
        usuario VARCHAR(30) NOT NULL UNIQUE,
        hash VARCHAR(255) NOT NULL COMMENT 'contraseña cifrada (scrypt), nunca la contraseña',
        rol ENUM('admin', 'usuario') NOT NULL DEFAULT 'usuario',
        sesion VARCHAR(32) NULL COMMENT 'sesión válida: al entrar en otro equipo se reemplaza',
        creado DATETIME NOT NULL,
        actualizado DATETIME NOT NULL
    ) CHARACTER SET utf8mb4""",
]


def ahora():
    return datetime.now(ECUADOR).replace(tzinfo=None, microsecond=0)


@contextmanager
def conexion():
    con = pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"), port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER"), password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get("DB_NAME", "sacardatos"), charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=True, connect_timeout=10)
    try:
        yield con.cursor()
    finally:
        con.close()


def crear_tablas():
    with conexion() as c:
        for sql in TABLAS:
            c.execute(sql)

def obtener_usuario(usuario):
    with conexion() as c:
        c.execute("SELECT * FROM usuarios WHERE usuario = %s", (usuario,))
        return c.fetchone()

def listar_usuarios():
    with conexion() as c:
        c.execute("SELECT usuario, rol, creado, actualizado "
                  "FROM usuarios ORDER BY usuario")
        return c.fetchall()

def contar_usuarios():
    with conexion() as c:
        c.execute("SELECT COUNT(*) AS n FROM usuarios")
        return c.fetchone()["n"]

def administradores():
    """Los administradores: siempre debe quedar al menos uno."""
    with conexion() as c:
        c.execute("SELECT usuario FROM usuarios WHERE rol = 'admin'")
        return [f["usuario"] for f in c.fetchall()]

def crear_usuario(usuario, hash_clave, rol="usuario"):
    with conexion() as c:
        c.execute("INSERT INTO usuarios (usuario, hash, rol, creado, actualizado) "
                  "VALUES (%s, %s, %s, %s, %s)",
                  (usuario, hash_clave, rol, ahora(), ahora()))

CAMPOS = {"hash", "rol"}

def actualizar_usuario(usuario, **campos):
    campos = {k: v for k, v in campos.items() if k in CAMPOS}
    if not campos:
        return
    asignaciones = ", ".join(f"{k} = %s" for k in campos)
    with conexion() as c:
        c.execute(f"UPDATE usuarios SET {asignaciones}, actualizado = %s WHERE usuario = %s",
                  (*campos.values(), ahora(), usuario))


def guardar_sesion(usuario, sesion):
    """Deja una sola sesión válida: la última que entró."""
    with conexion() as c:
        c.execute("UPDATE usuarios SET sesion = %s WHERE usuario = %s", (sesion, usuario))


def renombrar_usuario(viejo, nuevo):
    with conexion() as c:
        c.execute("UPDATE usuarios SET usuario = %s, actualizado = %s WHERE usuario = %s",
                  (nuevo, ahora(), viejo))


def eliminar_usuario(usuario):
    with conexion() as c:
        c.execute("DELETE FROM usuarios WHERE usuario = %s", (usuario,))


def migrar_json(ruta):
    ruta = Path(ruta)
    if not ruta.exists() or contar_usuarios():
        return 0
    usuarios = json.loads(ruta.read_text(encoding="utf-8"))
    for nombre, d in usuarios.items():
        crear_usuario(nombre, d["hash"], d.get("rol", "usuario"))
    ruta.rename(ruta.with_name(ruta.name + ".migrado"))
    return len(usuarios)
