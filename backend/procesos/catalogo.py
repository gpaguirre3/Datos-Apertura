import atexit
import io
import os
import re
import shutil
import tempfile
import threading
import uuid
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from descargas import consolidado
from descargas import descargar_certificados as isspol
from descargas import descargar_issfa as issfa
from descargas import descargar_mina as mina
from descargas import descargar_mina_familia as mina_familia
from descargas import descargar_mina_nombres as mina_nombres
from descargas import descargar_supa as supa
from descargas import portada
from documentos import montos_letras as montos
from documentos import primera_hoja
from documentos import unir_cedula
from documentos import unir_pdf

BASE = Path(tempfile.gettempdir()) / "sacardatos-trabajos"

VIDA_TRABAJO = timedelta(hours=2)  

ECUADOR = timezone(timedelta(hours=-5))  


def _limpiar_todo():
    shutil.rmtree(BASE, ignore_errors=True)


_limpiar_todo()  
atexit.register(_limpiar_todo)

trabajos = {}

_candado = threading.Lock()


def borrar_trabajo(tid):
    if re.fullmatch(r"[0-9a-f]{12}", tid or ""):
        shutil.rmtree(BASE / tid, ignore_errors=True)
    with _candado:
        trabajos.pop(tid, None)


def _caducar():
    limite = datetime.now(ECUADOR) - VIDA_TRABAJO
    with _candado:
        viejos = [tid for tid, t in trabajos.items()
                  if t["fin"] and (t.get("terminado") or t["fecha"]) < limite]
    for tid in viejos:
        borrar_trabajo(tid)


    for zip_viejo in BASE.glob("entrega_*.zip"):
        try:
            if datetime.fromtimestamp(zip_viejo.stat().st_mtime, ECUADOR) < limite:
                zip_viejo.unlink()
        except OSError:
            pass

# pagina: en qué pantalla sale · extension: qué archivo pide ·
# segundo_archivo: necesita un ZIP más · requiere_mina: depende del .env
CATALOGO = [
    {"clave": "isspol", "nombre": "ISSPOL", "detalle": "Policía Nacional",
     "pagina": "aperturas", "extension": ".xlsx"},
    {"clave": "issfa", "nombre": "ISSFA", "detalle": "Fuerzas Armadas",
     "pagina": "aperturas", "extension": ".xlsx"},
    {"clave": "supa", "nombre": "SUPA", "detalle": "Pensiones alimenticias",
     "pagina": "aperturas", "extension": ".xlsx"},
    {"clave": "portada", "nombre": "PORTADA",
     "detalle": "Mina, Aduana y Procesos judiciales",
     "pagina": "aperturas", "extension": ".xlsx", "requiere_mina": True},
    {"clave": "consolidado", "nombre": "Consolidado",
     "detalle": "ISSPOL + ISSFA + SUPA + PORTADA",
     "pagina": "aperturas", "extension": ".xlsx", "requiere_mina": True},
    {"clave": "mina_nombres", "nombre": "Mina Nombres", "solo_admin": True,
     "detalle": "Cédula → nombre",
     "pagina": "obtener-datos", "extension": ".xlsx", "requiere_mina": True},
    {"clave": "mina_familia", "nombre": "Datos para Solicitar Dato Seguro",
     "detalle": "Titular, cónyuge e hijos",
     "pagina": "obtener-datos", "extension": ".xlsx", "requiere_mina": True},
    {"clave": "montos", "nombre": "Montos a letras", "solo_admin": True,
     "detalle": "Monto → letras en dólares",
     "pagina": "obtener-datos", "extension": ".xlsx"},
    {"clave": "unir_pdf", "nombre": "Unir PDF",
     "detalle": "Varios PDF a UNO",
     "pagina": "obtener-datos", "extension": ".zip"},
    {"clave": "primera_hoja", "nombre": "Primera hoja", "solo_admin": True,
     "detalle": "Optener primera hoja de un pdf",
     "pagina": "obtener-datos", "extension": ".zip"},
    {"clave": "unir_cedula", "nombre": "Apertaras con Dato Seguro",
     "detalle": "Consolidado + Dato Seguro",
     "pagina": "obtener-datos", "extension": ".zip", "segundo_archivo": True,
     "ordenes": [{"valor": "consolidado", "texto": "el Consolidado + Dato Seguro"},
                 {"valor": "documento", "texto": "Dato Seguro + Consolidado"}]},
]

MODULOS = {"isspol": isspol, "issfa": issfa, "mina_nombres": mina_nombres,
           "mina_familia": mina_familia, "montos": montos, "supa": supa,
           "portada": portada, "consolidado": consolidado, "unir_pdf": unir_pdf,
           "unir_cedula": unir_cedula, "primera_hoja": primera_hoja}

NOMBRES = {MODULOS[c["clave"]]: c["nombre"] for c in CATALOGO}


class ErrorProceso(Exception):
    """Error del usuario (archivo, formato o permiso). El front lo recibe como 400."""


def por_clave(clave):
    return next((c for c in CATALOGO if c["clave"] == clave), None)


def mina_autorizado():
    return os.environ.get("MINA_AUTORIZADO", "").lower() in ("si", "sí", "true", "1")


def catalogo_publico(es_admin=False):
    autorizado = mina_autorizado()
    salida = []
    for c in CATALOGO:
        if c.get("solo_admin") and not es_admin:
            continue
        item = dict(c)
        item["disponible"] = autorizado or not c.get("requiere_mina")
        if not item["disponible"]:
            item["motivo"] = "Falta MINA_AUTORIZADO=si en el .env del servidor"
        salida.append(item)
    return salida


def _leer_cedulas(sitio, contenido, archivo2):
    if sitio is unir_cedula:
        return unir_cedula.leer_zips(contenido, archivo2)
    if sitio in (mina_nombres, mina_familia):
        # Una fila por fila del Excel, repetidas incluidas
        return isspol.leer_cedulas(io.BytesIO(contenido), unicas=False)
    lector = {issfa: issfa.leer_personas, consolidado: issfa.leer_personas,
              montos: montos.leer_montos, unir_pdf: unir_pdf.leer_zip,
              primera_hoja: unir_pdf.leer_zip}.get(sitio, isspol.leer_cedulas)
    return lector(io.BytesIO(contenido))

# Títulos de la vista previa, según lo que devuelve cada lector.
COLUMNAS = {
    "issfa": ["Cédula", "Nombre"],
    "consolidado": ["Cédula", "Nombre"],
    "montos": ["Fila del Excel", "Monto"],
    "unir_pdf": ["Archivo dentro del ZIP"],
    "primera_hoja": ["Archivo dentro del ZIP"],
    "unir_cedula": ["Cédula", "PDF del consolidado", "PDF de documentos"],
}
MUESTRA = 100 

def _preparar(clave, archivo, archivo2, es_admin=False):

    ficha = por_clave(clave) or por_clave("isspol")
    sitio = MODULOS[ficha["clave"]]
    extension = ficha["extension"]

    # El permiso se mira primero: sin él no hay nada que validar.
    if ficha.get("solo_admin") and not es_admin:
        raise ErrorProceso("Este proceso es solo para administradores.")
    if ficha.get("requiere_mina") and not mina_autorizado():
        raise ErrorProceso("Falta MINA_AUTORIZADO=si en el archivo .env del servidor")
    if not archivo or not (archivo.filename or "").lower().endswith(extension):
        raise ErrorProceso(f"Sube un archivo {extension}")
    if ficha.get("segundo_archivo") and (not archivo2 or not (archivo2.filename or "").lower().endswith(".zip")):
        raise ErrorProceso("Sube también el ZIP de documentos (.zip)")

    contenido = archivo.read()
    nombre_excel = re.sub(r"[^\w.\- ]", "_", Path(archivo.filename).stem) or "cedulas"
    try:
        datos = _leer_cedulas(sitio, contenido, archivo2.read() if archivo2 else None)
    except Exception as e:
        raise ErrorProceso(f"No se pudo leer el archivo: {e}") from e
    if not datos:
        raise ErrorProceso("No se encontraron datos en el archivo")
    return ficha, sitio, contenido, datos, nombre_excel


def _fila_legible(dato):
    if isinstance(dato, str):
        return [dato]
    campos = []
    for valor in dato:
        if isinstance(valor, (bytes, bytearray)):
            continue
        if isinstance(valor, (list, tuple)):
            campos.append(f"{len(valor)} archivo(s)")
        else:
            campos.append("" if valor is None else str(valor))
    return campos


def _nombres_del_excel(contenido):
    try:
        personas = issfa.leer_personas(io.BytesIO(contenido))
    except Exception:
        return {}
    nombres = {c: (n or "").strip() for c, n in personas if (n or "").strip()}
    return nombres


def previsualizar(clave, archivo, archivo2=None, es_admin=False):
    ficha, _, contenido, datos, _ = _preparar(clave, archivo, archivo2, es_admin)
    columnas = COLUMNAS.get(ficha["clave"], ["Cédula"])
    por_cedula = bool(datos) and isinstance(datos[0], str)

    if por_cedula:
        try:
            todas = isspol.leer_cedulas(io.BytesIO(contenido), unicas=False)
        except Exception:
            todas = datos
        unicos = list(dict.fromkeys(datos))
        veces_por_dato = Counter(todas)
        mostrados = unicos[:MUESTRA]
        veces = [veces_por_dato.get(d, 1) for d in mostrados]
        total, distintos, cuantos_hay = len(todas), len(unicos), len(unicos)

        nombres = _nombres_del_excel(contenido)
        if nombres and columnas == ["Cédula"]:
            columnas = ["Cédula", "Nombre"]
            filas = [[c, nombres.get(c, "")] for c in mostrados]
        else:
            filas = [_fila_legible(d) for d in mostrados]
    else:
        mostrados = datos[:MUESTRA]
        filas = [_fila_legible(d) for d in mostrados]
        total, distintos, cuantos_hay = len(datos), len(datos), len(datos)
        veces = [1] * len(mostrados)
        if ficha["clave"] in ("issfa", "consolidado"):
            try:
                todas = isspol.leer_cedulas(io.BytesIO(contenido), unicas=False)
                veces_por_dato = Counter(todas)
                veces = [veces_por_dato.get(f[0], 1) for f in filas]
                total = len(todas)
            except Exception:
                pass

    return {
        "proceso": ficha["nombre"],
        "columnas": columnas,
        "filas": filas,
        "veces": veces,
        "total": total,
        "distintos": distintos,
        "agrupada": por_cedula,
        "recortada": cuantos_hay > MUESTRA,
    }


def lanzar(clave, archivo, *, archivo2=None, orden="consolidado", usuario=None, es_admin=False):
    ficha, sitio, contenido, cedulas, nombre_excel = _preparar(clave, archivo, archivo2, es_admin)
    _caducar()

    tid = uuid.uuid4().hex[:12]
    cancelar = threading.Event()
    # El total cuenta las distintas: las repetidas se consultan una vez
    total = len(dict.fromkeys(cedulas)) if cedulas and isinstance(cedulas[0], str) else len(cedulas)
    estado = trabajos[tid] = {"total": total, "fin": False, "filas": {}, "cancelar": cancelar,
                              "nombre": ficha["nombre"], "fecha": datetime.now(ECUADOR),
                              "terminado": None, "usuario": usuario}

    def avanzar(cedula, est, detalle, clave_fila=None):
        with _candado:
            estado["filas"][clave_fila or cedula] = [cedula, est, detalle]

    def correr():
        try:
            extra = {"contenido": contenido, "nombre_excel": nombre_excel} if sitio in (mina_nombres, montos) else {}
            if sitio is unir_cedula:
                extra["documento_primero"] = orden == "documento"
            sitio.procesar(cedulas, BASE / tid, al_avanzar=avanzar, cancelado=cancelar.is_set, **extra)
            if sitio in (mina, consolidado, portada):
                carpeta_mina = BASE / tid if sitio is mina else consolidado.carpeta(BASE / tid, "Mina")
                edades = mina.leer_csv(carpeta_mina / "edades.csv", "edad")
                mina.excel_con_edades(contenido, edades, BASE / tid / f"{nombre_excel}_con_edad.xlsx")
        except Exception as e:
            with _candado:
                estado["filas"]["-"] = ["-", "ERROR", str(e)]
        finally:
            estado["terminado"] = datetime.now(ECUADOR)
            estado["fin"] = True

    threading.Thread(target=correr, daemon=True).start()
    return tid, ficha["nombre"], len(cedulas)


def estado(tid):
    t = trabajos.get(tid)
    if not t:
        return None
    with _candado:
        filas = list(t["filas"].values())
    ok = sum(f[1] in ("OK", "OMITIDO") for f in filas)
    errores = sum(f[1] in ("ERROR", "INCOMPLETO", isspol.SIN_CERTIFICADO) for f in filas)
    cancelados = sum(f[1] == "CANCELADO" for f in filas)
    return {"total": t["total"], "fin": t["fin"], "filas": filas, "ok": ok, "errores": errores,
            "reintentando": sum(f[1] == "REINTENTANDO" for f in filas),
            "cancelando": t["cancelar"].is_set(), "hechos": ok + errores + cancelados,
            "nombre": t["nombre"]}


def cancelar(tid):
    t = trabajos.get(tid)
    if not t:
        return None
    t["cancelar"].set()
    return t["nombre"]


def nombre_zip(tid, carpeta):
    t = trabajos.get(tid)
    if t:
        return f"certificados_{t['nombre']} {t['fecha']:%d-%m-%y}.zip"
    fecha = datetime.fromtimestamp(carpeta.stat().st_mtime, ECUADOR)
    return f"certificados {fecha:%d-%m-%y}.zip"


def comprimir(tid, borrar=False):
    carpeta = BASE / tid
    if not re.fullmatch(r"[0-9a-f]{12}", tid) or not carpeta.is_dir():
        return None
    nombre = nombre_zip(tid, carpeta)
    destino = BASE / f"entrega_{tid}.zip"
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for f in carpeta.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(carpeta))
    if borrar:
        borrar_trabajo(tid)
    return destino, nombre
