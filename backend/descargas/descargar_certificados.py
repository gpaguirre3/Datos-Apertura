import argparse
import base64
import csv
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright

def cargar_env(ruta=Path(__file__).resolve().parents[1] / ".env"):
    """Deja el .env en el entorno. Lo llaman todos los robots al importar este
    módulo, para que funcionen igual sueltos que lanzados desde la aplicación."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            # El # solo es comentario si va suelto: las URL llevan # dentro.
            valor = valor.split(" #")[0].strip().strip("\"'")
            os.environ.setdefault(clave.strip(), valor)


cargar_env()

URL = os.environ.get("ISSPOL_URL", "https://siisspolweb.isspol.org.ec/#/publico/reporteAfiliacionExterno")


def leer_cedulas(ruta_excel, columna=None, unicas=True):
    """Busca una columna llamada 'cedula'/'cédula'; si no existe usa la primera.
    Con unicas=False devuelve una cédula por fila del Excel, repetidas incluidas."""
    ws = load_workbook(ruta_excel, read_only=True, data_only=True).active
    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        return []

    encabezado = [str(c or "").strip().lower() for c in filas[0]]
    idx, inicio = 0, 0
    objetivo = (columna or "").strip().lower()
    for i, nombre in enumerate(encabezado):
        if (objetivo and nombre == objetivo) or (not objetivo and nombre in ("cedula", "cédula", "identificacion", "identificación")):
            idx, inicio = i, 1
            break
    else:
        # Si la primera celda no es numérica, es encabezado
        if not re.fullmatch(r"\d+(\.0)?", str(filas[0][0] or "").strip()):
            inicio = 1

    cedulas = []
    for fila in filas[inicio:]:
        if idx >= len(fila) or fila[idx] is None:
            continue
        valor = str(fila[idx]).strip()
        if valor.endswith(".0"):
            valor = valor[:-2]
        valor = re.sub(r"\D", "", valor)
        if not valor:
            continue
        # Excel elimina el 0 inicial (ej. cédulas de provincias 01-09)
        cedulas.append(valor.zfill(10))
    return list(dict.fromkeys(cedulas)) if unicas else cedulas  # en el orden del Excel

CAPTURA_JS = """
(() => {
  window.__pdfs = [];
  const guardar = (dataUrl) => { const b64 = (dataUrl || '').split(',')[1]; if (b64 && b64.startsWith('JVBER')) window.__pdfs.push(b64); };
  const orig = URL.createObjectURL;
  URL.createObjectURL = function (obj) {
    try {
      if (obj instanceof Blob) { const fr = new FileReader(); fr.onload = () => guardar(fr.result); fr.readAsDataURL(obj); }
    } catch (e) {}
    return orig.apply(this, arguments);
  };
  const abrir = window.open;
  window.open = function (url) {
    if (typeof url === 'string' && url.startsWith('data:')) guardar(url);
    return abrir.apply(this, arguments);
  };
})();
"""

PDF_B64 = re.compile(r"JVBERi0[A-Za-z0-9+/=\\]{100,}")


def pdf_en_respuesta(resp):
    """Bytes del PDF si la respuesta lo trae directo o en base64 dentro de un JSON/texto."""
    try:
        tipo = (resp.headers.get("content-type") or "").lower()
        if not any(t in tipo for t in ("pdf", "octet-stream", "json", "text/plain")):
            return None
        cuerpo = resp.body()
    except Exception:
        return None
    if cuerpo.startswith(b"%PDF"):
        return cuerpo
    m = PDF_B64.search(cuerpo.decode("latin-1"))
    if m:
        return base64.b64decode(m.group(0).replace("\\", ""))
    return None

AVISOS_SIN_CERTIFICADO = ("No se puede encontrar a la persona",)
SIN_CERTIFICADO = "SIN CERTIFICADO"

BUSCAR_AVISO = r"""avisos => {
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = w.nextNode());) {
    const e = n.parentElement;
    if (!e || ["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"].includes(e.tagName)) continue;
    if (!avisos.some(a => n.textContent.includes(a))) continue;
    const r = e.getBoundingClientRect();
    if (r.width && r.height && getComputedStyle(e).visibility !== "hidden") return e.innerText.trim();
  }
  return null;
}"""

def guardar_pdf(page, context, destino, timeout_ms):
    """Hace clic en Imprimir y captura el PDF: descarga, respuesta del servidor
    (directa o en base64), blob mostrado en un visor o pestaña nueva.
    Devuelve True si guardó el PDF, el texto del aviso si ISSPOL dice que no hay certificado,
    o False si no llegó nada."""
    capturado = {}

    def on_response(resp):
        if "pdf" not in capturado:
            pdf = pdf_en_respuesta(resp)
            if pdf:
                capturado["pdf"] = pdf

    def on_download(d):
        capturado["download"] = d

    context.on("response", on_response)
    page.on("download", on_download)
    try:
        page.get_by_role("button", name=re.compile("imprimir", re.I)).first.click(timeout=15000)

        fin = time.time() + timeout_ms / 1000
        while time.time() < fin:
            if "download" in capturado:
                capturado["download"].save_as(destino)
                return True
            if "pdf" in capturado:
                destino.write_bytes(capturado["pdf"])
                return True
            for p in context.pages:
                try:
                    blobs = p.evaluate("window.__pdfs || []")
                except Exception:
                    continue
                if blobs:
                    destino.write_bytes(base64.b64decode(blobs[-1]))
                    return True
            aviso = page.evaluate(BUSCAR_AVISO, list(AVISOS_SIN_CERTIFICADO))
            if aviso:
                return aviso
            page.wait_for_timeout(250)
        return False
    finally:
        context.remove_listener("response", on_response)
        page.remove_listener("download", on_download)
        for p in context.pages[1:]:
            p.close()


def mensaje_en_pantalla(page):
    """Devuelve el texto de alertas/toasts visibles (p. ej. 'cédula no encontrada')."""
    for sel in (".toast-message", ".swal2-html-container", ".swal2-title", ".alert-danger", ".ui-messages-error"):
        loc = page.locator(sel)
        if loc.count() and loc.first.is_visible():
            return loc.first.inner_text().strip()
    return ""


def captura_error(page, salida, cedula):
    """Guarda pantalla y HTML del error en <salida>/errores para poder diagnosticarlo."""
    carpeta = Path(salida) / "errores"
    carpeta.mkdir(exist_ok=True)
    try:
        page.screenshot(path=carpeta / f"{cedula}.png", full_page=True)
        (carpeta / f"{cedula}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass


def leer_proxy():
    """ISSPOL_PROXY=http://usuario:clave@host:puerto  o  socks5://127.0.0.1:1080"""
    valor = os.environ.get("ISSPOL_PROXY")
    if not valor:
        return None
    u = urlsplit(valor)
    proxy = {"server": f"{u.scheme}://{u.hostname}:{u.port}"}
    if u.username:
        proxy["username"] = unquote(u.username)
        proxy["password"] = unquote(u.password or "")
    return proxy


VENTANA_RESERVA = {"width": 1280, "height": 960}  # si no se puede leer la pantalla
VENTANA_MINIMA = {"width": 1024, "height": 700}  # por debajo no cabe un captcha
BARRA_NAVEGADOR = 120  # alto de pestañas y barra de direcciones


def ajustar_ventana(page):
    """Adapta la ventana del navegador a la pantalla del equipo, sea del tamaño que sea.

    Vale para cualquier robot que muestre la ventana. Devuelve qué se pudo hacer.
    """
    try:
        sesion = page.context.new_cdp_session(page)
        ventana = sesion.send("Browser.getWindowForTarget")["windowId"]
        sesion.send("Browser.setWindowBounds",
                    {"windowId": ventana, "bounds": {"windowState": "maximized"}})
        ancho, alto, usado = page.evaluate(
            "() => [screen.availWidth, screen.availHeight, innerWidth]")
        if usado >= ancho * 0.9:
            return "maximizada"
        # Sin gestor de ventanas maximizar no llena la pantalla: se fija a mano
        sesion.send("Browser.setWindowBounds", {"windowId": ventana, "bounds": {
            "windowState": "normal", "left": 0, "top": 0,
            "width": int(ancho), "height": int(alto)}})
        return "estirada a la pantalla"
    except Exception:
        pass
    try:
        ancho, alto = page.evaluate("() => [screen.availWidth, screen.availHeight]")
        page.set_viewport_size({
            "width": max(VENTANA_MINIMA["width"], int(ancho)),
            "height": max(VENTANA_MINIMA["height"], int(alto) - BARRA_NAVEGADOR),
        })
        return "ajustada a la pantalla"
    except Exception:
        return "con la medida de reserva"


CENTRAR_CAPTCHA = """() => {
  let movidos = 0;
  for (const marco of document.querySelectorAll("iframe")) {
    if (!/recaptcha/i.test(marco.src) || !/bframe/.test(marco.src)) continue;
    const caja = marco.parentElement;  // el div que lo pega a la casilla y lo saca de la pantalla
    if (!caja) continue;
    const ancho = marco.offsetWidth || 400, alto = marco.offsetHeight || 580;
    // En pantallas pequeñas se encoge lo justo para que quepa entero
    const escala = Math.min(1, (innerWidth - 24) / ancho, (innerHeight - 24) / alto);
    Object.assign(caja.style, {
      position: "fixed", left: "50%", top: "50%", right: "auto", bottom: "auto",
      transform: `translate(-50%, -50%) scale(${escala})`, margin: "0", zIndex: "2147483647",
    });
    movidos++;
  }
  return movidos;
}"""


def centrar_captcha(page):
    """Pone el reto de imágenes en el centro, para que no quede cortado en pantallas chicas."""
    try:
        return page.evaluate(CENTRAR_CAPTCHA)
    except Exception:
        return 0


REINTENTOS = 2  # intentos extra para las cédulas que fallan, al final de la pasada


def con_reintentos(items, cedula_de, intentar, salida, al_avanzar=None, reintentos=REINTENTOS,
                   extension="pdf", cancelado=None):
    salida = Path(salida)
    estados = {}

    def marcar(item, estado, detalle):
        cedula = cedula_de(item)
        estados[cedula] = (estado, detalle)
        print(f"{cedula}: {estado} - {detalle}")
        if al_avanzar:
            al_avanzar(cedula, estado, detalle)

    pendientes = []
    for item in items:
        if (salida / f"{cedula_de(item)}.{extension}").exists():
            marcar(item, "OMITIDO", "ya descargado")
        else:
            pendientes.append(item)

    total = reintentos + 1
    for intento in range(1, total + 1):
        if intento > 1:
            if not pendientes or (cancelado and cancelado()):
                break
            for item in pendientes:
                marcar(item, "REINTENTANDO", f"intento {intento} de {total}")
            time.sleep(5)  # dar un respiro al servidor antes de reintentar
        fallidos = []
        for i, item in enumerate(pendientes):
            if cancelado and cancelado():
                for resto in pendientes[i:]:
                    marcar(resto, "CANCELADO", "cancelado por el usuario")
                break
            estado, detalle = intentar(item)
            if estado == "ERROR":
                fallidos.append(item)
                if intento > 1:
                    detalle = f"{detalle} ({intento} intentos)"
            marcar(item, estado, detalle)
        pendientes = fallidos

    with open(salida / "resultado.csv", "w", newline="", encoding="utf-8-sig") as f:
        log = csv.writer(f)
        log.writerow(["cedula", "estado", "detalle"])
        log.writerows([c, *estados[c]] for c in estados)
    return salida / "resultado.csv"


def procesar(cedulas, salida, visible=False, espera=60, al_avanzar=None, cancelado=None):
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not visible, proxy=leer_proxy())
        context = browser.new_context(accept_downloads=True, ignore_https_errors=True)
        context.add_init_script(CAPTURA_JS)
        page = context.new_page()

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            browser.close()
            raise RuntimeError(
                "No hay conexión con siisspolweb.isspol.org.ec"
            )

        def intentar(cedula):
            destino = salida / f"{cedula}.pdf"
            try:
                # Rutas con '#': hay que pasar por about:blank para recargar de verdad
                page.goto("about:blank")
                page.goto(URL, wait_until="networkidle", timeout=60000)
                # Solo casillas visibles: las ocultas no hay que esperarlas
                campo = page.locator("input[type='text']:visible, input:not([type]):visible").first
                campo.wait_for(state="visible", timeout=60000)
                campo.fill("")
                campo.type(cedula, delay=30)

                resultado = guardar_pdf(page, context, destino, espera * 1000)
                if resultado is True:
                    return "OK", destino.name
                captura_error(page, salida, cedula)
                if resultado:  # aviso de ISSPOL: respuesta definitiva, no se reintenta
                    return SIN_CERTIFICADO, f"No se puede generar el certificado: {resultado}"
                return "ERROR", mensaje_en_pantalla(page) or "no se generó el PDF"
            except Exception as e:
                captura_error(page, salida, cedula)
                return "ERROR", str(e).splitlines()[0]
            finally:
                page.wait_for_timeout(1000)  # pausa para no saturar el servidor

        log_path = con_reintentos(cedulas, lambda c: c, intentar, salida, al_avanzar, cancelado=cancelado)
        browser.close()
    return log_path


def main():
    ap = argparse.ArgumentParser(description="Descarga certificados de afiliación ISSPOL desde un Excel")
    ap.add_argument("excel", help="Archivo .xlsx con las cédulas")
    ap.add_argument("--columna", help="Nombre de la columna con las cédulas (por defecto 'cedula' o la primera)")
    ap.add_argument("--salida", default="certificados", help="Carpeta donde guardar los PDF")
    ap.add_argument("--visible", action="store_true", help="Mostrar el navegador")
    ap.add_argument("--espera", type=int, default=60, help="Segundos máximos de espera por certificado")
    args = ap.parse_args()

    cedulas = leer_cedulas(args.excel, args.columna)
    if not cedulas:
        sys.exit("No se encontraron cédulas en el Excel.")

    print(f"{len(cedulas)} cédulas a procesar. PDFs en: {Path(args.salida).resolve()}")
    log_path = procesar(cedulas, args.salida, args.visible, args.espera)
    print(f"Listo. Resumen en {log_path}")


if __name__ == "__main__":
    main()
