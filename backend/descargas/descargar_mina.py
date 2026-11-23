import argparse
import csv
import io
import os
import re
import sys
from copy import copy
from pathlib import Path

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright

from .descargar_certificados import captura_error, con_reintentos, leer_cedulas, leer_proxy

BASE_URL = os.environ.get("MINA_URL", "http://186.4.213.167/Mina/")
CREAR = BASE_URL + "#Consulta/create"


def texto_datos(page):
    partes = [t.strip() for t in page.locator(".field[data-name^='datos']").all_inner_texts()]
    return "\n\n".join(t for t in partes if t and t.lower() not in ("none", "ninguno"))

RECT_REGISTRO_CIVIL = r"""() => {
  const campo = document.querySelector(".field[data-name='datos']");
  if (!campo) return null;
  const titulo = [...campo.querySelectorAll("h1, h2, h3")].find(e => /registro civil/i.test(e.innerText));
  if (!titulo) return null;
  let tabla = titulo.nextElementSibling;
  while (tabla && tabla.tagName !== "TABLE") tabla = tabla.nextElementSibling;
  const partes = [document.querySelector("label[data-name='datos']"), titulo, tabla].filter(Boolean)
    .map(e => e.getBoundingClientRect());
  const m = 8;
  const x = Math.min(...partes.map(r => r.left)) - m, y = Math.min(...partes.map(r => r.top)) - m;
  const w = Math.max(...partes.map(r => r.right)) + m - x, h = Math.max(...partes.map(r => r.bottom)) + m - y;
  return { x: Math.max(0, x + scrollX), y: Math.max(0, y + scrollY), width: w, height: h };
}"""

LEER_EDAD = r"""() => {
  const celdas = [...document.querySelectorAll(".field[data-name^='datos'] th, .field[data-name^='datos'] td")];
  for (const rotulo of ["edad", "edad:"]) {
    const celda = celdas.find(c => c.innerText.trim().toLowerCase() === rotulo && c.nextElementSibling?.tagName === "TD");
    const valor = celda?.nextElementSibling.innerText.trim();
    if (valor && /^\d+$/.test(valor)) return valor;
  }
  return null;
}"""


def leer_csv(ruta, columna):
    if not Path(ruta).exists():
        return {}
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        return {fila["cedula"]: fila[columna] for fila in csv.DictReader(f)}


def excel_con_edades(contenido, edades, destino, columna=None):
    excel_con_columna(contenido, {c: int(e) for c, e in edades.items()}, destino, "edad", columna)


def excel_con_columna(contenido, valores, destino, titulo, columna=None):
    wb = load_workbook(io.BytesIO(contenido))
    ws = wb.active
    encabezado = [str(c.value or "").strip().lower() for c in ws[1]]
    claves = ((columna or "").strip().lower(),) if columna else ("cedula", "cédula", "identificacion", "identificación")
    i_ced = next((i for i, n in enumerate(encabezado) if n in claves), 0)
    tiene_encabezado = any(encabezado) and not re.fullmatch(r"\d+(\.0)?", encabezado[i_ced])
    nueva = ws.max_column + 1
    if tiene_encabezado:
        ws.cell(1, nueva, titulo).font = copy(ws.cell(1, i_ced + 1).font)
    for fila in range(2 if tiene_encabezado else 1, ws.max_row + 1):
        valor = str(ws.cell(fila, i_ced + 1).value or "").strip()
        valor = re.sub(r"\D", "", valor[:-2] if valor.endswith(".0") else valor)
        if valor and valor.zfill(10) in valores:
            ws.cell(fila, nueva, valores[valor.zfill(10)])
    wb.save(destino)


def captura_registro_civil(page, destino):
    rect = page.evaluate(RECT_REGISTRO_CIVIL)
    if rect:
        page.screenshot(path=destino, full_page=True, clip=rect)
        return True
    page.screenshot(path=destino, full_page=True)
    return False


def aviso_espo(page):
    for sel in ("#notification .alert", ".alert-danger", ".popover-content"):
        loc = page.locator(sel)
        if loc.count() and loc.first.is_visible():
            return loc.first.inner_text().strip()
    return ""


def iniciar_sesion(page, usuario, clave):
    page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
    if page.locator("#btn-login").count():
        page.fill("#field-userName", usuario)
        page.fill("#field-password", clave)
        page.click("#btn-login")
    try:
        page.locator("#btn-login").wait_for(state="detached", timeout=30000)
    except Exception:
        raise RuntimeError("No se pudo iniciar sesión en Mina: revisa usuario y contraseña.")


def credenciales(usuario=None, clave=None):
    usuario = usuario or os.environ.get("MINA_USUARIO")
    clave = clave or os.environ.get("MINA_CLAVE")
    if not usuario or not clave:
        raise RuntimeError("Faltan las credenciales de Mina (MINA_USUARIO y MINA_CLAVE).")
    return usuario, clave


def abrir_consulta(page, cedula, creados, salida, espera, usuario, clave):
    if cedula in creados:
        page.goto(creados[cedula], wait_until="networkidle", timeout=60000)
    else:
        page.goto("about:blank")
        page.goto(CREAR, wait_until="networkidle", timeout=60000)
        if page.locator("#btn-login").count():  # la sesión expiró
            iniciar_sesion(page, usuario, clave)
            page.goto(CREAR, wait_until="networkidle", timeout=60000)
        campo = page.locator("input[data-name='cedula']").first
        campo.wait_for(state="visible", timeout=60000)
        campo.fill(cedula)
        page.locator("button[data-action='save']").first.click()
        try:
            page.wait_for_url(re.compile(r"#Consulta/view/"), timeout=espera * 1000)
        except Exception:
            captura_error(page, salida, cedula)
            return None, aviso_espo(page) or "no se pudo guardar la consulta"
        creados[cedula] = page.url

    for _ in range(max(1, espera // 5)):
        page.locator(".field[data-name='datos']").first.wait_for(state="attached", timeout=60000)
        page.wait_for_timeout(1000)
        texto = texto_datos(page)
        if texto:
            return texto, None
        page.wait_for_timeout(5000)
        page.reload(wait_until="networkidle")
    captura_error(page, salida, cedula)
    return None, "la consulta no devolvió datos"


def procesar(cedulas, salida, visible=False, espera=60, al_avanzar=None, usuario=None, clave=None, cancelado=None):
    usuario, clave = credenciales(usuario, clave)

    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    creados = {}  
    datos = leer_csv(salida / "datos.csv", "datos")
    edades = leer_csv(salida / "edades.csv", "edad")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not visible, proxy=leer_proxy())
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        iniciar_sesion(page, usuario, clave)

        def intentar(cedula):
            try:
                texto, error = abrir_consulta(page, cedula, creados, salida, espera, usuario, clave)
                if error:
                    return "ERROR", error

                recortada = captura_registro_civil(page, salida / f"{cedula}.png")
                datos[cedula] = texto
                edad = page.evaluate(LEER_EDAD)
                if edad:
                    edades[cedula] = edad
                return "OK", f"{cedula}.png" if recortada else f"{cedula}.png (sin sección Registro Civil: página completa)"
            except Exception as e:
                captura_error(page, salida, cedula)
                return "ERROR", str(e).splitlines()[0]
            finally:
                page.wait_for_timeout(1000)  # pausa para no saturar el servidor

        # La captura .png indica que ya se consultó (no se repite la consulta)
        log_path = con_reintentos(cedulas, lambda c: c, intentar, salida, al_avanzar, extension="png",
                                  cancelado=cancelado)
        browser.close()

    with open(salida / "datos.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["cedula", "datos"])
        w.writerows(datos.items())
    with open(salida / "edades.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["cedula", "edad"])
        w.writerows(edades.items())
    return log_path


def main():
    ap = argparse.ArgumentParser(description="Consulta masiva de cédulas en Mina con captura de pantalla")
    ap.add_argument("excel", help="Archivo .xlsx con las cédulas")
    ap.add_argument("--columna", help="Nombre de la columna con las cédulas (por defecto 'cedula' o la primera)")
    ap.add_argument("--salida", default="consultas_mina", help="Carpeta donde guardar las capturas")
    ap.add_argument("--usuario", help="Usuario de Mina (o variable MINA_USUARIO)")
    ap.add_argument("--clave", help="Contraseña de Mina (o variable MINA_CLAVE)")
    ap.add_argument("--visible", action="store_true", help="Mostrar el navegador")
    ap.add_argument("--espera", type=int, default=60, help="Segundos máximos de espera por consulta")
    ap.add_argument("--autorizado", action="store_true",
                    help="Declaro que tengo autorización de los titulares para consultar sus datos")
    args = ap.parse_args()

    if not args.autorizado and os.environ.get("MINA_AUTORIZADO", "").lower() not in ("si", "sí", "true", "1"):
        sys.exit("Falta la autorización: usa --autorizado o pon MINA_AUTORIZADO=si en el .env.")
    cedulas = leer_cedulas(args.excel, args.columna)
    if not cedulas:
        sys.exit("No se encontraron cédulas en el Excel.")

    print(f"{len(cedulas)} cédulas a consultar. Capturas en: {Path(args.salida).resolve()}")
    log_path = procesar(cedulas, args.salida, args.visible, args.espera, usuario=args.usuario, clave=args.clave)
    print(f"Listo. Resumen en {log_path}")


if __name__ == "__main__":
    main()
