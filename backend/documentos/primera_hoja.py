import argparse
import csv
import re
import sys
from pathlib import Path

try:  
    import pymupdf as fitz
except ImportError:
    import fitz

from .unir_pdf import leer_zip  

UNIDO = "primeras_hojas.pdf"

def nombre_salida(nombre, usados):
    base = re.sub(r"[^\w.\- ]", "_", Path(nombre.replace("\\", "/")).stem).strip() or "documento"
    final, n = f"{base}.pdf", 2
    while final.lower() in usados or final.lower() == UNIDO:
        final, n = f"{base}_{n}.pdf", n + 1
    usados.add(final.lower())
    return final


def procesar(items, salida, al_avanzar=None, cancelado=None):
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    unido = fitz.open()
    usados = set()

    with open(salida / "resultado.csv", "w", newline="", encoding="utf-8-sig") as f:
        log = csv.writer(f)
        log.writerow(["orden", "archivo", "estado", "detalle"])
        for n, (nombre, contenido) in enumerate(items, 1):
            if cancelado and cancelado():
                estado, detalle = "CANCELADO", "cancelado por el usuario"
            else:
                try:
                    with fitz.open(stream=contenido, filetype="pdf") as doc:
                        if doc.needs_pass:
                            raise ValueError("tiene contraseña")
                        if len(doc) == 0:
                            raise ValueError("no tiene hojas")
                        with fitz.open() as hoja:
                            hoja.insert_pdf(doc, from_page=0, to_page=0)
                            archivo = nombre_salida(nombre, usados)
                            hoja.save(salida / archivo, garbage=3, deflate=True)
                        unido.insert_pdf(doc, from_page=0, to_page=0)
                        estado, detalle = "OK", f"{archivo}: hoja 1 de {len(doc)}"
                except Exception as e:  # PDF dañado o protegido: se salta y se avisa
                    estado, detalle = "ERROR", f"no se pudo leer: {str(e).splitlines()[0]}"
            log.writerow([n, nombre, estado, detalle])
            if al_avanzar:
                al_avanzar(nombre, estado, detalle, clave=n)

    if len(unido):
        unido.save(salida / UNIDO, garbage=3, deflate=True)
    unido.close()
    return salida / "resultado.csv"


def main():
    ap = argparse.ArgumentParser(description="Deja solo la primera hoja de cada PDF de un ZIP")
    ap.add_argument("zip", help="Archivo .zip con los PDF")
    ap.add_argument("--salida", default="primeras_hojas", help="Carpeta donde guardar el resultado")
    args = ap.parse_args()

    items = leer_zip(args.zip)
    if not items:
        sys.exit("El ZIP no tiene archivos PDF.")
    procesar(items, args.salida)
    print(f"Listo. PDF en {args.salida}")


if __name__ == "__main__":
    main()
