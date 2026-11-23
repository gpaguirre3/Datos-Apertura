import argparse
import csv
import shutil
import sys
import zipfile
from pathlib import Path

try: 
    import pymupdf as fitz
except ImportError:
    import fitz

from . import descargar_aduana as aduana
from . import descargar_certificados as isspol
from . import descargar_issfa as issfa
from . import descargar_judicial as judicial
from . import descargar_mina as mina
from . import descargar_supa as supa

CONSULTAS = [
    ("Procesos judiciales", judicial, "png", False),
    ("ISSPOL", isspol, "pdf", False),
    ("ISSFA", issfa, "pdf", True),
    ("SUPA", supa, "pdf", False),
    ("Mina", mina, "png", False),
    ("Aduana", aduana, "png", False),
]

PORTADA = [c for c in CONSULTAS if c[0] in ("Mina", "Aduana", "Procesos judiciales")]

ORDEN_PDF = ["SUPA", "ISSPOL", "ISSFA"]
LOTE = 10
ORDEN_IMAGENES = ["Mina", "Aduana", "Procesos judiciales"]
INDIVIDUALES = "individuales.zip"

A4 = fitz.paper_rect("a4")
MARGEN, SEPARACION = 36, 18 


def carpeta(salida, nombre):
    return Path(salida) / "partes" / nombre.lower().replace(" ", "_")


def agregar_imagenes(doc, imagenes):
    if not imagenes:
        return
    ancho_util, alto_util = A4.width - 2 * MARGEN, A4.height - 2 * MARGEN
    proporciones = [] 
    for ruta in imagenes:
        pix = fitz.Pixmap(str(ruta))
        proporciones.append(pix.height / pix.width)
    espacio_imagenes = alto_util - SEPARACION * (len(imagenes) - 1)
    ancho = min(ancho_util, espacio_imagenes / sum(proporciones))

    pagina, y = doc.new_page(width=A4.width, height=A4.height), MARGEN
    x = MARGEN + (ancho_util - ancho) / 2
    for ruta, proporcion in zip(imagenes, proporciones):
        alto = ancho * proporcion
        pagina.insert_image(fitz.Rect(x, y, x + ancho, y + alto), filename=str(ruta))
        y += alto + SEPARACION


def armar_pdf(cedula, salida, destino, consultas=CONSULTAS):
    pedidas = [n for n, *_ in consultas]
    doc = fitz.open()
    imagenes = [(n, carpeta(salida, n) / f"{cedula}.png")
                for n in ORDEN_IMAGENES if n in pedidas]
    imagenes = [(n, r) for n, r in imagenes if r.exists()]
    agregar_imagenes(doc, [r for _, r in imagenes])
    incluidas = [n for n, _ in imagenes]
    for nombre in [n for n in ORDEN_PDF if n in pedidas]:
        parte = carpeta(salida, nombre) / f"{cedula}.pdf"
        if parte.exists():
            with fitz.open(parte) as pdf:
                doc.insert_pdf(pdf)
            incluidas.append(nombre)
    if incluidas:
        doc.save(destino, garbage=3, deflate=True)
    doc.close()
    return incluidas


def procesar(personas, salida, al_avanzar=None, cancelado=None, consultas=CONSULTAS,
             nombre_todos="consolidado_todos.pdf"):
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    cedulas = [c for c, _ in personas]
    resultados = {c: {} for c in cedulas}  
    finales = {}  
    no_disponibles = {}  

    def avisar(cedula, estado, detalle):
        if al_avanzar:
            al_avanzar(cedula, estado, detalle)

    for inicio in range(0, len(personas), LOTE):
        if cancelado and cancelado():
            break
        lote = personas[inicio:inicio + LOTE]
        cedulas_lote = [c for c, _ in lote]

        for nombre, modulo, extension, con_nombre in consultas:
            if cancelado and cancelado():
                break
            if nombre in no_disponibles:
                for cedula in cedulas_lote:
                    resultados[cedula][nombre] = ("ERROR", no_disponibles[nombre])
                continue

            def avance(cedula, estado, detalle, _nombre=nombre):
                if estado in ("OK", "OMITIDO", "ERROR", isspol.SIN_CERTIFICADO):
                    resultados[cedula][_nombre] = (estado, detalle)
                avisar(cedula, "CAPTCHA" if estado == "CAPTCHA" else "EN PROCESO", f"{_nombre}: {detalle}")

            try:
                modulo.procesar(lote if con_nombre else cedulas_lote, carpeta(salida, nombre),
                                al_avanzar=avance, cancelado=cancelado)
            except Exception as e:  
                no_disponibles[nombre] = str(e).splitlines()[0]
                for cedula in cedulas_lote:
                    resultados[cedula].setdefault(nombre, ("ERROR", no_disponibles[nombre]))
                    avisar(cedula, "EN PROCESO", f"{nombre}: no disponible")

        for cedula in cedulas_lote:
            incluidas = armar_pdf(cedula, salida, salida / f"{cedula}.pdf", consultas)
            faltan = [n for n, *_ in consultas if n not in incluidas]
            if not incluidas:
                estado = "CANCELADO" if cancelado and cancelado() else "ERROR"
                finales[cedula] = (estado, "no se obtuvo ninguna consulta")
            elif faltan:
                finales[cedula] = ("INCOMPLETO", f"{cedula}.pdf sin: {', '.join(faltan)}")
            else:
                finales[cedula] = ("OK", f"{cedula}.pdf con las {len(consultas)} consultas")
            avisar(cedula, *finales[cedula])

    with open(salida / "resultado.csv", "w", newline="", encoding="utf-8-sig") as f:
        log = csv.writer(f)
        log.writerow(["cedula", "estado", "detalle", *[n for n, *_ in consultas]])
        for cedula in cedulas:
            if cedula not in finales:  # su lote no llegó a empezar
                finales[cedula] = ("CANCELADO", "cancelado por el usuario")
                avisar(cedula, *finales[cedula])
            partes = [" - ".join(resultados[cedula].get(n, ("SIN HACER", ""))) for n, *_ in consultas]
            log.writerow([cedula, *finales[cedula], *partes])

    unir_todos(cedulas, salida, salida / nombre_todos)
    shutil.rmtree(salida / "partes", ignore_errors=True)
    empaquetar(cedulas, salida)
    return salida / "resultado.csv"


def empaquetar(cedulas, salida):
    """Deja los PDF por cédula dentro de un zip y los quita de la carpeta."""
    pdfs = [salida / f"{c}.pdf" for c in cedulas]
    pdfs = [p for p in pdfs if p.exists()]
    if not pdfs:
        return None
    destino = salida / INDIVIDUALES
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for pdf in pdfs:
            z.write(pdf, pdf.name)
            pdf.unlink()
    return destino


def unir_todos(cedulas, salida, destino):
    todos = fitz.open()
    for cedula in cedulas:
        pdf = salida / f"{cedula}.pdf"
        if pdf.exists():
            with fitz.open(pdf) as doc:
                todos.insert_pdf(doc)
    if len(todos):
        todos.save(destino, garbage=3, deflate=True)
    todos.close()


def main():
    ap = argparse.ArgumentParser(description="Hace todas las consultas por cédula y arma un PDF por cédula")
    ap.add_argument("excel", help="Archivo .xlsx con columnas cedula y nombre")
    ap.add_argument("--salida", default="consolidado", help="Carpeta donde guardar los PDF")
    args = ap.parse_args()

    personas = issfa.leer_personas(args.excel)
    if not personas:
        sys.exit("No se encontraron cédulas en el Excel.")
    print(f"{len(personas)} cédulas. PDF en: {Path(args.salida).resolve()}")
    print(f"Listo. Resumen en {procesar(personas, args.salida)}")


if __name__ == "__main__":
    main()
