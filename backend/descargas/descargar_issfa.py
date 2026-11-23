import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright

from .descargar_certificados import captura_error, con_reintentos, leer_proxy

URL = os.environ.get("ISSFA_URL", "https://ias.issfa.mil.ec/certificados/Formulario.jsf")


def leer_personas(ruta_excel, columna=None):
    ws = load_workbook(ruta_excel, read_only=True, data_only=True).active
    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        return []

    encabezado = [str(c or "").strip().lower() for c in filas[0]]
    objetivo = (columna or "").strip().lower()
    claves = (objetivo,) if objetivo else ("cedula", "cédula", "identificacion", "identificación")
    i_ced = next((i for i, n in enumerate(encabezado) if n in claves), None)
    i_nom = next((i for i, n in enumerate(encabezado) if "nombre" in n), None)
    tiene_encabezado = i_ced is not None or i_nom is not None or not re.fullmatch(r"\d+(\.0)?", str(filas[0][0] or "").strip())
    if i_ced is None:
        i_ced = 0

    personas = {}
    for fila in filas[1 if tiene_encabezado else 0:]:
        if i_ced >= len(fila) or fila[i_ced] is None:
            continue
        cedula = str(fila[i_ced]).strip()
        if cedula.endswith(".0"):
            cedula = cedula[:-2]
        cedula = re.sub(r"\D", "", cedula)
        if not cedula:
            continue
        nombre = ""
        if i_nom is not None and i_nom < len(fila) and fila[i_nom] is not None:
            nombre = " ".join(str(fila[i_nom]).split()).upper()
        personas.setdefault(cedula.zfill(10), nombre)  # Excel elimina el 0 inicial
    return list(personas.items())


def procesar(personas, salida, visible=False, espera=60, al_avanzar=None, cancelado=None):
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not visible, proxy=leer_proxy())
        # El certificado SSL del sitio tiene la cadena incompleta
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            browser.close()
            raise RuntimeError("No hay conexión con ias.issfa.mil.ec desde este equipo.")

        def intentar(persona):
            cedula, nombre = persona
            try:
                page.goto(URL, wait_until="domcontentloaded", timeout=60000)
                page.fill("[id='form1:cedula']", cedula)
                page.fill("[id='form1:nombre']", nombre)
                with page.expect_navigation(timeout=espera * 1000):
                    page.click("[id='form1:consultar']")
                page.wait_for_load_state("domcontentloaded")

                # Con certificado, la respuesta trae un <embed src="pdf\\certificado...pdf">
                embed = page.locator("embed[src], iframe[src], object[data]").first
                try:
                    embed.wait_for(state="attached", timeout=10000)
                except Exception:
                    captura_error(page, salida, cedula)
                    return "ERROR", mensaje_issfa(page)

                src = embed.get_attribute("src") or embed.get_attribute("data")
                pdf_url = urljoin(page.url, src.strip().replace("\\", "/"))
                resp = context.request.get(pdf_url, timeout=espera * 1000)
                cuerpo = resp.body()
                if not cuerpo.startswith(b"%PDF"):
                    raise RuntimeError(f"el servidor no devolvió un PDF (HTTP {resp.status})")
                destino = salida / f"{cedula}.pdf"
                destino.write_bytes(cuerpo)
                return "OK", destino.name
            except Exception as e:
                captura_error(page, salida, cedula)
                return "ERROR", str(e).splitlines()[0]
            finally:
                page.wait_for_timeout(1000)  # pausa para no saturar el servidor

        log_path = con_reintentos(personas, lambda p: p[0], intentar, salida, al_avanzar, cancelado=cancelado)
        browser.close()
    return log_path


def mensaje_issfa(page):
    try:
        texto = page.inner_text("body")
    except Exception:
        return "no se generó el PDF"
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea.startswith(("No se", "Error", "El ", "La ", "Debe", "Ingrese un")) and "Ingrese el nombre unicamente" not in linea:
            return linea
    return "no se generó el PDF"


def main():
    ap = argparse.ArgumentParser(description="Descarga certificados de afiliación ISSFA desde un Excel")
    ap.add_argument("excel", help="Archivo .xlsx con columnas de cédula y nombre")
    ap.add_argument("--columna", help="Nombre de la columna con las cédulas (por defecto 'cedula' o la primera)")
    ap.add_argument("--salida", default="certificados_issfa", help="Carpeta donde guardar los PDF")
    ap.add_argument("--visible", action="store_true", help="Mostrar el navegador")
    ap.add_argument("--espera", type=int, default=60, help="Segundos máximos de espera por certificado")
    args = ap.parse_args()

    personas = leer_personas(args.excel, args.columna)
    if not personas:
        sys.exit("No se encontraron cédulas en el Excel.")

    print(f"{len(personas)} cédulas a procesar. PDFs en: {Path(args.salida).resolve()}")
    log_path = procesar(personas, args.salida, args.visible, args.espera)
    print(f"Listo. Resumen en {log_path}")


if __name__ == "__main__":
    main()
