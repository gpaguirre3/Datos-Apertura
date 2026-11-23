import argparse
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from .descargar_certificados import captura_error, con_reintentos, leer_cedulas, leer_proxy

URL = os.environ.get("JUDICIAL_URL", "https://procesosjudiciales.funcionjudicial.gob.ec/busqueda-filtros")
SIN_RESULTADOS = "La consulta no devolvió resultados"
ESPERA_CAPTCHA = 180  # segundos para que la persona marque el captcha
PAUSA_ENTRE_CONSULTAS = 15  # segundos entre una búsqueda y la siguiente, a ritmo de persona

ESTADO_JS = """([sinResultados, captchaPosible]) => {
  const texto = document.body.innerText;
  if (texto.includes("Registros encontrados")) return "resultados";
  if (texto.includes(sinResultados)) return "vacio";
  const captcha = document.querySelector("iframe[title='reCAPTCHA']");
  if (captchaPosible && captcha && captcha.getBoundingClientRect().height > 0) return "captcha";
  return null;
}"""

RECT_CONTENIDO = r"""() => {
  const nav = [...document.querySelectorAll("a, button")].find(e => /Búsqueda avanzada/.test(e.innerText));
  let menu = nav;
  while (menu && menu.getBoundingClientRect().height < innerHeight * 0.6) menu = menu.parentElement;
  const desde = menu ? menu.getBoundingClientRect().right : 0;
  const hojas = ["INPUT", "TEXTAREA", "BUTTON", "IMG", "svg", "MAT-ICON"];
  let x1 = Infinity, y1 = Infinity, x2 = 0, y2 = 0;
  for (const e of document.body.querySelectorAll("*")) {
    if (e.children.length && !hojas.includes(e.tagName)) continue;
    if (!hojas.includes(e.tagName) && !e.textContent.trim()) continue;
    const r = e.getBoundingClientRect(), st = getComputedStyle(e);
    if (!r.width || !r.height || st.visibility === "hidden" || r.left < desde - 1) continue;
    x1 = Math.min(x1, r.left); y1 = Math.min(y1, r.top); x2 = Math.max(x2, r.right); y2 = Math.max(y2, r.bottom);
  }
  if (x1 === Infinity) return null;
  const m = 16;
  return { x: Math.max(0, x1 - m + scrollX), y: Math.max(0, y1 - m + scrollY), width: x2 - x1 + 2 * m, height: y2 - y1 + 2 * m };
}"""

RECT_RESULTADOS = r"""() => {
  const conTexto = t => {
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n; (n = w.nextNode());) if (n.textContent.includes(t)) return n.parentElement;
    return null;
  };
  const filtros = conTexto("Filtros de búsqueda"), registros = conTexto("Registros encontrados");
  if (!filtros || !registros) return null;
  let bloque = filtros;
  while (bloque && !bloque.contains(registros)) bloque = bloque.parentElement;
  if (!bloque || bloque === document.body) return null;
  const desde = filtros.getBoundingClientRect().top;
  let x1 = Infinity, y1 = Infinity, x2 = 0, y2 = 0;
  for (const e of bloque.querySelectorAll("*")) {
    const r = e.getBoundingClientRect();
    // Solo lo que empieza en "Filtros de búsqueda" o más abajo (deja fuera "Regresar")
    if (!r.width || !r.height || r.top < desde - 12 || getComputedStyle(e).visibility === "hidden") continue;
    x1 = Math.min(x1, r.left); y1 = Math.min(y1, r.top); x2 = Math.max(x2, r.right); y2 = Math.max(y2, r.bottom);
  }
  if (x1 === Infinity) return null;
  const m = 16, arriba = 4;  // poco margen arriba: justo encima está "Regresar"
  return { x: Math.max(0, x1 - m + scrollX), y: Math.max(0, y1 - arriba + scrollY), width: x2 - x1 + 2 * m, height: y2 - y1 + arriba + m };
}"""


def mostrar_todo(page):
    try:
        selector = page.locator("mat-paginator mat-select, .mat-mdc-paginator mat-select").first
        if not selector.count():
            return
        antes = page.inner_text("body")
        selector.click()
        opciones = page.locator("mat-option")
        opciones.first.wait_for(state="visible", timeout=5000)
        opciones.last.click()
        # Espera a que la lista se redibuje, no a que la red quede quieta
        page.wait_for_function("t => document.body.innerText !== t", arg=antes, timeout=8000)
        page.wait_for_timeout(300)
    except Exception:
        page.keyboard.press("Escape")  # si no se pudo, se captura la primera página

SUBIR = """() => {
  scrollTo(0, 0);
  for (const e of document.querySelectorAll("*")) if (e.scrollTop) e.scrollTop = 0;
}"""


def captura(page, destino, rect_js=RECT_CONTENIDO):
    """Solo la zona con contenido; la página completa si no se puede calcular."""
    page.evaluate(SUBIR)
    rect = page.evaluate(rect_js)
    page.screenshot(path=destino, full_page=True, clip=rect) if rect else page.screenshot(path=destino, full_page=True)


def hay_pantalla():
    return not sys.platform.startswith("linux") or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def procesar(cedulas, salida, visible=True, espera=60, al_avanzar=None, cancelado=None):
    if not hay_pantalla():
        raise RuntimeError("Procesos judiciales pide un captcha que debes marcar tú: "
                           "ejecuta la app en tu PC (no en el servidor) para que se abra el navegador.")
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, proxy=leer_proxy(), args=["--window-position=0,0"])
        page = browser.new_page(viewport={"width": 1280, "height": 560}, device_scale_factor=2)

        ultima = {"busqueda": 0.0}  # cuándo empezó la búsqueda anterior

        def esperar_turno(cedula):
            """Deja pasar PAUSA_ENTRE_CONSULTAS desde la búsqueda anterior. False si se canceló."""
            falta = ultima["busqueda"] + PAUSA_ENTRE_CONSULTAS - time.time()
            if falta > 0 and al_avanzar:
                al_avanzar(cedula, "EN ESPERA", f"esperando {round(falta)} s antes de consultar")
            while time.time() < ultima["busqueda"] + PAUSA_ENTRE_CONSULTAS:
                if cancelado and cancelado():
                    return False
                time.sleep(0.5)
            ultima["busqueda"] = time.time()
            return True

        def intentar(cedula):
            if not esperar_turno(cedula):
                return "CANCELADO", "cancelado por el usuario"
            try:
                page.goto(URL, wait_until="domcontentloaded", timeout=60000)
                page.get_by_placeholder("Ingrese la identificación del Actor/Ofendido").fill(cedula, timeout=60000)
                buscar = page.locator("button:has-text('BUSCAR')").first

                def resolver_captcha():
                    """Espera a que la persona marque el captcha (BUSCAR vuelve a habilitarse)."""
                    if al_avanzar:
                        al_avanzar(cedula, "CAPTCHA", "marca 'No soy un robot' en la ventana del navegador")
                    print(f"{cedula}: marca 'No soy un robot' en la ventana del navegador...")
                    page.bring_to_front()
                    captcha = page.locator("iframe[title='reCAPTCHA']").first
                    if captcha.count():
                        captcha.evaluate("e => e.scrollIntoView({block: 'center'})")  # a la vista para marcarlo
                    limite = time.time() + ESPERA_CAPTCHA
                    while not buscar.is_enabled():
                        if time.time() > limite or (cancelado and cancelado()):
                            return False
                        page.wait_for_timeout(500)
                    return True

                def esperar(captcha_posible):
                    return page.wait_for_function(ESTADO_JS, arg=[SIN_RESULTADOS, captcha_posible],
                                                  timeout=espera * 1000).json_value()

                if not buscar.is_enabled() and not resolver_captcha():
                    return "ERROR", "no se resolvió el captcha a tiempo"
                buscar.click()
                if esperar(True) == "captcha":
                    if not resolver_captcha():
                        return "ERROR", "no se resolvió el captcha a tiempo"
                    buscar.click()
                    esperar(False)

                texto = page.inner_text("body")
                if SIN_RESULTADOS in texto:
                    captura(page, salida / f"{cedula}.png")  # de inmediato: el aviso se cierra solo
                    return "OK", "Sin procesos: la consulta no devolvió resultados"
                page.wait_for_timeout(500)  # que termine de dibujar la lista
                mostrar_todo(page)
                captura(page, salida / f"{cedula}.png", RECT_RESULTADOS)
                texto = page.inner_text("body")
                m = re.search(r"Registros encontrados:\s*(\d+)", texto)
                detalle = f"{m.group(1) if m else '?'} proceso(s) encontrado(s)"
                paginas = re.search(r"Página\s+\d+\s+de\s+(\d+)", texto)
                if paginas and int(paginas.group(1)) > 1:
                    detalle += f" (la captura muestra la página 1 de {paginas.group(1)})"
                return "OK", detalle
            except Exception as e:
                captura_error(page, salida, cedula)
                return "ERROR", str(e).splitlines()[0]
            finally:
                page.wait_for_timeout(500)  # pausa breve entre consultas

        log_path = con_reintentos(cedulas, lambda c: c, intentar, salida, al_avanzar,
                                  extension="png", cancelado=cancelado)
        browser.close()
    return log_path


def main():
    ap = argparse.ArgumentParser(description="Consulta de procesos judiciales por cédula del Actor/Ofendido")
    ap.add_argument("excel", help="Archivo .xlsx con las cédulas")
    ap.add_argument("--columna", help="Nombre de la columna con las cédulas (por defecto 'cedula' o la primera)")
    ap.add_argument("--salida", default="consultas_judicial", help="Carpeta donde guardar las capturas")
    ap.add_argument("--espera", type=int, default=60, help="Segundos máximos de espera por consulta")
    args = ap.parse_args()

    cedulas = leer_cedulas(args.excel, args.columna)
    if not cedulas:
        sys.exit("No se encontraron cédulas en el Excel.")

    print(f"{len(cedulas)} cédulas a consultar. Capturas en: {Path(args.salida).resolve()}")
    log_path = procesar(cedulas, args.salida, espera=args.espera)
    print(f"Listo. Resumen en {log_path}")


if __name__ == "__main__":
    main()
