import argparse
import csv
import io
import sys
import zipfile
from pathlib import Path

try: 
    import pymupdf as fitz
except ImportError:
    import fitz
from openpyxl import load_workbook

MAX_ARCHIVOS = 2000
MAX_TOTAL = 1024 ** 3  


def orden_de_excel(contenido):
    ws = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True).active
    nombres = [str(f[0]).strip() for f in ws.iter_rows(values_only=True) if f and f[0] not in (None, "")]
    nombres = [Path(n.replace("\\", "/")).name.lower() for n in nombres]
    return [n if n.endswith(".pdf") else n + ".pdf" for n in nombres]


def leer_zip(archivo, columna=None):
    with zipfile.ZipFile(archivo) as z:
        entradas = [i for i in z.infolist()
                    if not i.is_dir() and i.filename.lower().endswith(".pdf")
                    and not i.filename.startswith("__MACOSX/") and not Path(i.filename).name.startswith("._")]
        if len(entradas) > MAX_ARCHIVOS:
            raise ValueError(f"el ZIP tiene más de {MAX_ARCHIVOS} PDF")
        if sum(i.file_size for i in entradas) > MAX_TOTAL:
            raise ValueError("el ZIP es demasiado grande (más de 1 GB descomprimido)")
        excel = next((i for i in z.infolist() if i.filename.lower().endswith(".xlsx")
                      and not i.filename.startswith("__MACOSX/") and not Path(i.filename).name.startswith(("~$", "._"))), None)
        if excel:
            lista = orden_de_excel(z.read(excel))
            posicion = {n: p for p, n in reversed(list(enumerate(lista)))}
            # Los que faltan en la lista van al final; sort es estable
            entradas.sort(key=lambda i: posicion.get(Path(i.filename).name.lower(), len(lista)))
        return [(i.filename, z.read(i)) for i in entradas]


def procesar(items, salida, al_avanzar=None, cancelado=None):
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    unido = fitz.open()

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
                        desde = len(unido) + 1
                        unido.insert_pdf(doc)
                        estado, detalle = "OK", f"{len(doc)} hoja(s): páginas {desde} a {len(unido)} del PDF unido"
                except Exception as e:  # PDF dañado o protegido: se salta y se avisa
                    estado, detalle = "ERROR", f"no se pudo unir: {str(e).splitlines()[0]}"
            log.writerow([n, nombre, estado, detalle])
            if al_avanzar:
                al_avanzar(nombre, estado, detalle, clave=n)

    if len(unido):
        unido.save(salida / "pdf_unido.pdf", garbage=3, deflate=True)
    unido.close()
    return salida / "resultado.csv"


def main():
    ap = argparse.ArgumentParser(description="Une en un solo PDF los PDF de un ZIP, en orden por nombre")
    ap.add_argument("zip", help="Archivo .zip con los PDF")
    ap.add_argument("--salida", default="pdf_unido", help="Carpeta donde guardar el resultado")
    args = ap.parse_args()

    items = leer_zip(args.zip)
    if not items:
        sys.exit("El ZIP no tiene archivos PDF.")
    procesar(items, args.salida)
    print(f"Listo. PDF en {Path(args.salida) / 'pdf_unido.pdf'}")

if __name__ == "__main__":
    main()
