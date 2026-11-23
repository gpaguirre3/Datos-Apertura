import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from .descargar_certificados import captura_error, con_reintentos, leer_cedulas, leer_proxy

URL = os.environ.get("SUPA_URL", "https://supa.funcionjudicial.gob.ec/pensiones/publico/consulta.jsf")
SIN_RESULTADOS = "No se encuentra resultados."

def procesar(cedulas, salida, visible=False, espera=60, al_avanzar=None, cancelado=None):
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, proxy=leer_proxy())
        page = browser.new_page(viewport={"width": 1320, "height": 1000}, ignore_https_errors=True)

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            browser.close()
            raise RuntimeError("No hay conexión con supa.funcionjudicial.gob.ec desde este equipo.")

        def intentar(cedula):
            try:
                page.goto(URL, wait_until="domcontentloaded", timeout=60000)
                page.fill("[id='form:t_texto_cedula']", cedula, timeout=60000)
                # La búsqueda es un POST (AJAX de PrimeFaces) que redibuja el panel de resultados
                with page.expect_response(lambda r: r.request.method == "POST", timeout=espera * 1000):
                    page.click("[id='form:b_buscar_cedula']")
                filas = page.locator("[id='form:pResultado'] .ui-datatable-data > tr")
                filas.first.wait_for(state="visible", timeout=espera * 1000)
                page.wait_for_timeout(800)

                # Como Ctrl+P > Guardar como PDF: A4 vertical con colores de fondo (cabe en una hoja)
                page.pdf(path=salida / f"{cedula}.pdf", format="A4", print_background=True)

                if page.locator("[id='form:pResultado'] .ui-datatable-empty-message").count():
                    return "OK", f"Sin tarjetas: {SIN_RESULTADOS}"
                # Solo la primera celda de cada fila: la columna Intervinientes trae otra tabla adentro
                codigos = [t.strip() for t in filas.evaluate_all("rs => rs.map(r => r.cells[0]?.innerText || '')") if t.strip()]
                detalle = f"{len(codigos)} tarjeta(s): {', '.join(codigos)}"
                if page.locator("[id='form:pResultado'] .ui-paginator-top .ui-paginator-page").count() > 1:
                    detalle += " (hay más páginas: el PDF muestra solo la primera)"
                return "OK", detalle
            except Exception as e:
                captura_error(page, salida, cedula)
                return "ERROR", str(e).splitlines()[0]
            finally:
                page.wait_for_timeout(1000)  # pausa para no saturar el servidor

        log_path = con_reintentos(cedulas, lambda c: c, intentar, salida, al_avanzar,
                                  extension="pdf", cancelado=cancelado)
        browser.close()
    return log_path


def main():
    ap = argparse.ArgumentParser(description="Consulta masiva de tarjetas de pensión alimenticia en el SUPA")
    ap.add_argument("excel", help="Archivo .xlsx con las cédulas")
    ap.add_argument("--columna", help="Nombre de la columna con las cédulas (por defecto 'cedula' o la primera)")
    ap.add_argument("--salida", default="consultas_supa", help="Carpeta donde guardar los PDF")
    ap.add_argument("--visible", action="store_true", help="Mostrar el navegador")
    ap.add_argument("--espera", type=int, default=60, help="Segundos máximos de espera por consulta")
    args = ap.parse_args()

    cedulas = leer_cedulas(args.excel, args.columna)
    if not cedulas:
        sys.exit("No se encontraron cédulas en el Excel.")

    print(f"{len(cedulas)} cédulas a consultar. PDF en: {Path(args.salida).resolve()}")
    log_path = procesar(cedulas, args.salida, args.visible, args.espera)
    print(f"Listo. Resumen en {log_path}")


if __name__ == "__main__":
    main()
