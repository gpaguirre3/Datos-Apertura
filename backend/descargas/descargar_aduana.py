import argparse
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

from .descargar_certificados import captura_error, con_reintentos, leer_cedulas, leer_proxy

URL = os.environ.get("ADUANA_URL", "https://www.aduana.gob.ec/consultacupos/")

# Rectángulo desde el panel "Consulta por cédula" hasta el panel "Resultado"
RECT_RESULTADO = r"""() => {
  const resultado = document.querySelector("#div_resultado .panel");
  const consulta = document.querySelector("#txtCedula")?.closest(".panel");
  const partes = [consulta, resultado].filter(Boolean).map(e => e.getBoundingClientRect());
  if (!resultado) return null;
  const m = 6;
  const x = Math.min(...partes.map(r => r.left)) - m, y = Math.min(...partes.map(r => r.top)) - m;
  const w = Math.max(...partes.map(r => r.right)) + m - x, h = Math.max(...partes.map(r => r.bottom)) + m - y;
  return { x: Math.max(0, x + scrollX), y: Math.max(0, y + scrollY), width: w, height: h };
}"""


@contextmanager
def pantalla():
    """Variables de entorno para abrir un navegador con ventana; en Linux sin
    pantalla levanta un Xvfb temporal."""
    if not sys.platform.startswith("linux") or os.environ.get("DISPLAY"):
        yield None
        return
    if not shutil.which("Xvfb"):
        raise RuntimeError("Aduana necesita un navegador con ventana: instala Xvfb (apt install xvfb).")
    lectura, escritura = os.pipe()
    xvfb = subprocess.Popen(["Xvfb", "-displayfd", str(escritura), "-screen", "0", "1280x1024x24", "-nolisten", "tcp"],
                            pass_fds=(escritura,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.close(escritura)
    try:
        numero = os.read(lectura, 16).decode().strip()  # Xvfb escribe el número de pantalla libre que eligió
        os.close(lectura)
        yield {**os.environ, "DISPLAY": f":{numero}"}
    finally:
        xvfb.terminate()
        xvfb.wait()


def procesar(cedulas, salida, visible=False, espera=60, al_avanzar=None, cancelado=None):
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)

    with pantalla() as entorno, sync_playwright() as pw:
        args = [] if visible or entorno else ["--window-position=-32000,-32000"]
        browser = pw.chromium.launch(headless=False, env=entorno, args=args, proxy=leer_proxy())
        page = browser.new_page(viewport={"width": 1280, "height": 1000})

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            browser.close()
            raise RuntimeError("No hay conexión con www.aduana.gob.ec desde este equipo.")
        if "blocked" in page.title().lower():
            browser.close()
            raise RuntimeError("La Aduana bloqueó el acceso automático desde este equipo.")

        def intentar(cedula):
            try:
                page.goto(URL, wait_until="domcontentloaded", timeout=60000)
                page.check("input[name=tipo_consulta][value=COUR]")  # demás usuarios Courier
                page.fill("#txtCedula", cedula)
                page.click("#btnConsultar")
                resultado = page.locator("#div_resultado .panel")
                resultado.filter(has_text=cedula).wait_for(state="visible", timeout=espera * 1000)
                page.wait_for_timeout(500)

                page.screenshot(path=salida / f"{cedula}.png", full_page=True, clip=page.evaluate(RECT_RESULTADO))
                mensaje = resultado.locator("text=Mensaje").locator("xpath=following-sibling::*[1]")
                texto = mensaje.inner_text().strip() if mensaje.count() else ""
                return "OK", texto or f"{cedula}.png"
            except Exception as e:
                captura_error(page, salida, cedula)
                return "ERROR", str(e).splitlines()[0]
            finally:
                page.wait_for_timeout(1000)  # pausa para no saturar el servidor

        log_path = con_reintentos(cedulas, lambda c: c, intentar, salida, al_avanzar,
                                  extension="png", cancelado=cancelado)
        browser.close()
    return log_path


def main():
    ap = argparse.ArgumentParser(description="Consulta masiva de cupos Courier en la Aduana del Ecuador")
    ap.add_argument("excel", help="Archivo .xlsx con las cédulas")
    ap.add_argument("--columna", help="Nombre de la columna con las cédulas (por defecto 'cedula' o la primera)")
    ap.add_argument("--salida", default="consultas_aduana", help="Carpeta donde guardar las capturas")
    ap.add_argument("--visible", action="store_true", help="Mostrar el navegador")
    ap.add_argument("--espera", type=int, default=60, help="Segundos máximos de espera por consulta")
    args = ap.parse_args()

    cedulas = leer_cedulas(args.excel, args.columna)
    if not cedulas:
        sys.exit("No se encontraron cédulas en el Excel.")

    print(f"{len(cedulas)} cédulas a consultar. Capturas en: {Path(args.salida).resolve()}")
    log_path = procesar(cedulas, args.salida, args.visible, args.espera)
    print(f"Listo. Resumen en {log_path}")


if __name__ == "__main__":
    main()
