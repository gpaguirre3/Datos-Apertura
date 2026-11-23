import json
import os
import threading
from pathlib import Path

from .db import ahora

CARPETA = Path(__file__).resolve().parents[1] / "registros"
MAXIMO = 20_000  # registros que se conservan en cada archivo

_candado = threading.Lock()


def _ruta(tabla):
    if tabla not in ("accesos", "cambios"):
        raise ValueError(f"Registro desconocido: {tabla}")
    return CARPETA / f"{tabla}.json"


def leer(tabla):
    try:
        with _ruta(tabla).open(encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, list) else []
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError):
        return []


def _agregar(tabla, fila):
    with _candado:
        filas = leer(tabla)
        filas.append(fila)
        if len(filas) > MAXIMO:
            filas = filas[-MAXIMO:]
        CARPETA.mkdir(exist_ok=True)
        destino = _ruta(tabla)
        temporal = destino.with_suffix(".json.tmp")
        with temporal.open("w", encoding="utf-8") as f:
            json.dump(filas, f, ensure_ascii=False, indent=1)
        os.replace(temporal, destino)


def _fecha():
    return ahora().strftime("%Y-%m-%d %H:%M:%S")


def registrar_acceso(usuario, ip, navegador, resultado):
    _agregar("accesos", {"fecha": _fecha(), "usuario": usuario[:60], "ip": (ip or "")[:45],
                         "navegador": (navegador or "")[:255], "resultado": resultado})


def registrar_cambio(usuario, ip, accion, objetivo=None, detalle=None):
    _agregar("cambios", {"fecha": _fecha(), "usuario": usuario[:60], "ip": (ip or "")[:45],
                         "accion": accion[:40], "objetivo": (objetivo or "")[:120],
                         "detalle": detalle})


def ultimo_acceso_por_usuario():
    ultimo = {}
    for fila in leer("accesos"):
        if fila.get("resultado") == "OK":
            ultimo[fila.get("usuario")] = fila.get("fecha")
    return ultimo
