import argparse
import os
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from playwright.sync_api import sync_playwright

from .descargar_certificados import captura_error, con_reintentos, leer_cedulas, leer_proxy
from .descargar_mina import abrir_consulta, credenciales, excel_con_columna, iniciar_sesion

LEER_NOMBRE = r"""() => {
  const celdas = [...document.querySelectorAll(".field[data-name^='datos'] th, .field[data-name^='datos'] td")];
  for (const rotulo of ["nombre completo", "nombres:"]) {
    const celda = celdas.find(c => c.innerText.trim().toLowerCase() === rotulo);
    const valor = celda?.nextElementSibling;
    if (valor?.tagName === "TD" && valor.innerText.trim()) return valor.innerText.trim();
  }
  return null;
}"""


def guardar_excel(cedulas, nombres, ruta):
    wb = Workbook()
    ws = wb.active
    ws.title = "Nombres"
    ws.append(["cedula", "nombre"])
    for celda in ws[1]:
        celda.font = Font(bold=True)
    for cedula in cedulas:
        ws.append([cedula, nombres.get(cedula, "")])  # la cédula va como texto para conservar el 0 inicial
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 48
    wb.save(ruta)


def procesar(cedulas, salida, visible=False, espera=60, al_avanzar=None, cancelado=None,
             contenido=None, nombre_excel="cedulas", columna=None):
    usuario, clave = credenciales()
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    creados = {}  # cedula -> URL del registro, para no crear consultas duplicadas al reintentar
    nombres = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not visible, proxy=leer_proxy())
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        iniciar_sesion(page, usuario, clave)

        def intentar(cedula):
            try:
                _, error = abrir_consulta(page, cedula, creados, salida, espera, usuario, clave)
                if error:
                    return "ERROR", error
                nombre = page.evaluate(LEER_NOMBRE)
                if not nombre:
                    captura_error(page, salida, cedula)
                    return "ERROR", "la consulta no trae el nombre"
                nombres[cedula] = nombre
                return "OK", nombre
            except Exception as e:
                captura_error(page, salida, cedula)
                return "ERROR", str(e).splitlines()[0]
            finally:
                page.wait_for_timeout(1000)  # pausa para no saturar el servidor

        log_path = con_reintentos(list(dict.fromkeys(cedulas)), lambda c: c, intentar, salida, al_avanzar,
                                  extension="sin-archivo", cancelado=cancelado)
        browser.close()

    guardar_excel(cedulas, nombres, salida / "nombres.xlsx")  # una fila por fila del Excel subido
    if contenido:
        excel_con_columna(contenido, nombres, salida / f"{nombre_excel}_con_nombre.xlsx", "nombre", columna)
    return log_path


def main():
    ap = argparse.ArgumentParser(description="Obtiene los nombres de una lista de cédulas desde Mina")
    ap.add_argument("excel", help="Archivo .xlsx con las cédulas")
    ap.add_argument("--columna", help="Nombre de la columna con las cédulas (por defecto 'cedula' o la primera)")
    ap.add_argument("--salida", default="nombres_mina", help="Carpeta donde guardar el resultado")
    ap.add_argument("--visible", action="store_true", help="Mostrar el navegador")
    ap.add_argument("--espera", type=int, default=60, help="Segundos máximos de espera por consulta")
    args = ap.parse_args()

    if os.environ.get("MINA_AUTORIZADO", "").lower() not in ("si", "sí", "true", "1"):
        sys.exit("Falta MINA_AUTORIZADO=si en el .env.")
    cedulas = leer_cedulas(args.excel, args.columna)
    if not cedulas:
        sys.exit("No se encontraron cédulas en el Excel.")

    print(f"{len(cedulas)} cédulas a consultar. Resultado en: {Path(args.salida).resolve()}")
    procesar(cedulas, args.salida, args.visible, args.espera)
    print(f"Listo. Nombres en {Path(args.salida) / 'nombres.xlsx'}")


if __name__ == "__main__":
    main()
