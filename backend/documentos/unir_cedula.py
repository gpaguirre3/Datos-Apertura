import argparse
import csv
import io
import re
import sys
import zipfile
from pathlib import Path

try: 
    import pymupdf as fitz
except ImportError:
    import fitz

MAX_ARCHIVOS = 4000
MAX_TOTAL = 2 * 1024 ** 3  
IGNORAR = ("partes/", "errores/", "__macosx/")  
CEDULAS_POR_PDF = 10


def cedula_de(nombre):
    m = re.search(r"\d{9,13}", Path(nombre).stem)
    return m.group(0).zfill(10) if m else None


def pdfs_del_zip(contenido, consolidado):
    por_cedula, orden_csv, total = {}, [], 0
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        entradas = [i for i in z.infolist() if not i.is_dir()]
        if len(entradas) > MAX_ARCHIVOS:
            raise ValueError(f"un ZIP tiene más de {MAX_ARCHIVOS} archivos")
        for i in entradas:
            ruta = i.filename.replace("\\", "/").lower()
            nombre = Path(ruta).name
            if consolidado and (any(c in ruta for c in IGNORAR) or nombre.startswith("consolidado_todos")):
                continue
            if consolidado and nombre == "resultado.csv":
                texto = z.read(i).decode("utf-8-sig", errors="replace")
                orden_csv = [f.get("cedula", "").strip().zfill(10) for f in csv.DictReader(io.StringIO(texto))
                             if f.get("cedula", "").strip().isdigit()]
                continue
            if not nombre.endswith(".pdf") or nombre.startswith("._"):
                continue
            cedula = cedula_de(nombre)
            if not cedula:
                continue
            total += i.file_size
            if total > MAX_TOTAL:
                raise ValueError("los ZIP son demasiado grandes (más de 2 GB descomprimidos)")
            por_cedula.setdefault(cedula, []).append(z.read(i))
    return por_cedula, orden_csv


def leer_zips(zip_consolidado, zip_documentos):
    consolidados, orden = pdfs_del_zip(zip_consolidado, consolidado=True)
    documentos, _ = pdfs_del_zip(zip_documentos, consolidado=False)
    cedulas = list(dict.fromkeys([c for c in orden if c in consolidados or c in documentos]
                                 + list(consolidados) + list(documentos)))
    return [(c, consolidados.get(c, []), documentos.get(c, [])) for c in cedulas]


def procesar(items, salida, al_avanzar=None, cancelado=None, documento_primero=False):
    salida = Path(salida)
    (salida / "por_cedula").mkdir(parents=True, exist_ok=True)
    parte = {"doc": fitz.open(), "numero": 1, "cedulas": 0, "desde": 1}  # PDF que se está llenando

    def cerrar_parte():
        if parte["cedulas"]:
            hasta = parte["desde"] + parte["cedulas"] - 1
            parte["doc"].save(salida / f"unido_{parte['numero']:02d}_cedulas_{parte['desde']}-{hasta}.pdf",
                              garbage=3, deflate=True)
            parte["numero"] += 1
            parte["desde"] = hasta + 1
        parte["doc"].close()
        parte.update(doc=fitz.open(), cedulas=0)

    with open(salida / "resultado.csv", "w", newline="", encoding="utf-8-sig") as f:
        log = csv.writer(f)
        log.writerow(["orden", "cedula", "estado", "detalle", "pdf_parte", "paginas_en_la_parte"])
        for n, (cedula, consolidados, documentos) in enumerate(items, 1):
            if cancelado and cancelado():
                estado, detalle, paginas, archivo = "CANCELADO", "cancelado por el usuario", "", ""
            else:
                partes = [("documento", documentos), ("consolidado", consolidados)]
                if not documento_primero:
                    partes.reverse()
                uno, hojas, problemas = fitz.open(), {}, []
                for tipo, lista in partes:
                    for pdf in lista:
                        try:
                            with fitz.open(stream=pdf, filetype="pdf") as doc:
                                if doc.needs_pass:
                                    raise ValueError("tiene contraseña")
                                uno.insert_pdf(doc)
                                hojas[tipo] = hojas.get(tipo, 0) + len(doc)
                        except Exception as e:
                            problemas.append(f"{tipo} dañado ({str(e).splitlines()[0]})")
                faltan = [t for t, lista in partes if not lista]
                if len(uno):
                    uno.save(salida / "por_cedula" / f"{cedula}.pdf", garbage=3, deflate=True)
                    todo = parte["doc"]
                    desde = len(todo) + 1
                    todo.insert_pdf(uno)
                    paginas = f"{desde}-{len(todo)}"
                    archivo = f"parte {parte['numero']}"
                    parte["cedulas"] += 1
                    if parte["cedulas"] == CEDULAS_POR_PDF:
                        cerrar_parte()
                else:
                    paginas, archivo = "", ""
                uno.close()
                resumen = " + ".join(f"{t} ({hojas[t]} hoja(s))" for t, _ in partes if t in hojas)
                avisos = [f"falta el {t}" for t in faltan] + problemas
                if not hojas:
                    estado, detalle = "ERROR", "; ".join(avisos) or "sin PDF"
                elif avisos:
                    estado, detalle = "INCOMPLETO", f"{resumen}; " + "; ".join(avisos)
                else:
                    estado, detalle = "OK", resumen
            log.writerow([n, cedula, estado, detalle, archivo, paginas])
            if al_avanzar:
                al_avanzar(cedula, estado, detalle + (f" · {archivo}, páginas {paginas}" if paginas else ""))

    cerrar_parte()  
    parte["doc"].close()
    return salida / "resultado.csv"


def main():
    ap = argparse.ArgumentParser(description="Une por cédula los PDF del Consolidado con otros documentos")
    ap.add_argument("consolidado", help="ZIP descargado de la opción Consolidado")
    ap.add_argument("documentos", help="ZIP con PDF nombrados con la cédula")
    ap.add_argument("--documento-primero", action="store_true", help="poner el documento antes del consolidado")
    ap.add_argument("--salida", default="unido_por_cedula", help="Carpeta donde guardar el resultado")
    args = ap.parse_args()

    items = leer_zips(Path(args.consolidado).read_bytes(), Path(args.documentos).read_bytes())
    if not items:
        sys.exit("No se encontraron PDF con cédula en los ZIP.")
    procesar(items, args.salida, documento_primero=args.documento_primero)
    print(f"Listo. PDF en {Path(args.salida)} (unido_XX_cedulas_*.pdf)")


if __name__ == "__main__":
    main()
