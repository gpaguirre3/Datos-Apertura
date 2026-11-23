import argparse
import os
import sys
import unicodedata
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from playwright.sync_api import sync_playwright

from .descargar_certificados import captura_error, con_reintentos, leer_cedulas, leer_proxy
from .descargar_mina import abrir_consulta, credenciales, iniciar_sesion

EDAD_MAX_HIJOS = 64

LEER_FAMILIA = r"""() => {
  const norm = t => (t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim().replace(/:$/, "").trim().toLowerCase();
  const d1 = document.querySelector(".field[data-name='datos']");
  const d2 = document.querySelector(".field[data-name='datos2']");
  const valorEn = (campo, rotulo) => {
    if (!campo) return "";
    for (const c of campo.querySelectorAll("th, td"))
      if (norm(c.innerText) === rotulo && c.nextElementSibling?.tagName === "TD") {
        const v = c.nextElementSibling.innerText.trim();
        if (v) return v;
      }
    return "";
  };
  const registro = { cedula: valorEn(d1, "cedula"), nombre: valorEn(d1, "nombre completo"),
                     edad: valorEn(d1, "edad"), estado_civil: valorEn(d1, "estado civil") };
  const generales = { cedula: valorEn(d2, "identificacion"), nombre: valorEn(d2, "nombres"),
                      edad: valorEn(d2, "edad"), estado_civil: valorEn(d2, "estado civil") };
  const titular = registro.nombre ? { ...registro, fuente: "Registro Civil" }
                : generales.nombre ? { ...generales, fuente: "Datos Generales" } : null;

  // Filas de una tabla con columnas por nombre de cabecera
  const leerTabla = (tabla, columnas) => {
    const filas = [...tabla.rows];
    const cab = [...filas[0].cells].map(c => norm(c.innerText));
    const idx = Object.fromEntries(Object.entries(columnas).map(([k, n]) => [k, cab.findIndex(t => t.startsWith(n))]));
    return filas.slice(1).map(f => {
      const c = [...f.cells].map(x => x.innerText.trim());
      return { cedula: c[idx.cedula] || "", parentesco: c[idx.parentesco] || "",
               nombre: (c[idx.nombre] || "").replace(/\s+/g, " "), edad: c[idx.edad] || "" };
    }).filter(f => f.cedula || f.nombre);
  };
  let familia = [], fuenteFamilia = "";
  // Árbol Genealógico: la tabla que sigue al título, sin pasar a la sección siguiente
  const titulo = d1 && [...d1.querySelectorAll("h1, h2, h3")].find(e => /arbol geneal/.test(norm(e.innerText)));
  let tabla = titulo && titulo.nextElementSibling;
  while (tabla && tabla.tagName !== "TABLE" && !/^H[1-3]$/.test(tabla.tagName)) tabla = tabla.nextElementSibling;
  if (tabla && tabla.tagName === "TABLE") {
    familia = leerTabla(tabla, { cedula: "cedula", parentesco: "tipo", nombre: "nombre", edad: "edad" });
    fuenteFamilia = "Árbol Genealógico";
  }
  if (!familia.length && d2) {
    const arbol2 = [...d2.querySelectorAll("table")].find(t => t.rows.length &&
      [...t.rows[0].cells].some(c => norm(c.innerText) === "relacion"));
    if (arbol2) {
      familia = leerTabla(arbol2, { cedula: "cedula", parentesco: "relacion", nombre: "nombre", edad: "edad" });
      fuenteFamilia = "Datos de Arbol";
    }
  }
  return { titular, familia, fuente_familia: fuenteFamilia };
}"""

COLUMNAS = ["cedula_consultada", "nombre_titular", "edad_titular", "estado_civil",
            "parentesco", "cedula_familiar", "nombre_familiar", "edad_familiar"]


def sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.upper()) if unicodedata.category(c) != "Mn")


def edad(texto):
    return int(texto) if str(texto).strip().isdigit() else None


def elegir_familiares(familia):
    elegidos = []
    for f in familia:
        tipo = sin_tildes(f["parentesco"])
        if "CONYUGE" in tipo:
            elegidos.append({**f, "parentesco": "CONYUGE"})
        elif tipo.startswith("HIJ"):  # HIJO / HIJA (en Datos de Arbol vienen como Hijo / Hija)
            e = edad(f["edad"])
            if e is None or e <= EDAD_MAX_HIJOS:
                elegidos.append({**f, "parentesco": tipo})
    return elegidos


def guardar_excel(cedulas, resultados, ruta):
    wb = Workbook()
    ws = wb.active
    ws.title = "Familia"
    ws.append(COLUMNAS)
    for celda in ws[1]:
        celda.font = Font(bold=True)
    for cedula in cedulas:  # en el orden del Excel; la cédula va como texto para conservar el 0
        r = resultados.get(cedula)
        if not r:
            ws.append([cedula, "", "", "", "", "", "", ""])
            continue
        t = r["titular"]
        base = [cedula, t["nombre"], edad(t["edad"]), t["estado_civil"]]
        for f in r["familiares"] or [None]:
            ws.append(base + ([f["parentesco"], f["cedula"], f["nombre"], edad(f["edad"])] if f else ["", "", "", ""]))
    for letra, ancho in zip("ABCDEFGH", (14, 38, 10, 14, 12, 14, 38, 10)):
        ws.column_dimensions[letra].width = ancho
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(ruta)


def procesar(cedulas, salida, visible=False, espera=60, al_avanzar=None, cancelado=None):
    usuario, clave = credenciales()
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    creados = {}  # cedula -> URL del registro, para no crear consultas duplicadas al reintentar
    resultados = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not visible, proxy=leer_proxy())
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        iniciar_sesion(page, usuario, clave)

        def intentar(cedula):
            try:
                _, error = abrir_consulta(page, cedula, creados, salida, espera, usuario, clave)
                if error:
                    return "ERROR", error
                # Mina llena "Datos 2" antes que "Datos": si falta el titular, se recarga
                datos = page.evaluate(LEER_FAMILIA)
                for _ in range(max(1, espera // 5)):
                    if datos and datos["titular"] and (datos["familia"] or datos["titular"]["fuente"] == "Registro Civil"):
                        break
                    page.wait_for_timeout(5000)
                    page.reload(wait_until="networkidle")
                    page.locator(".field[data-name='datos']").first.wait_for(state="attached", timeout=60000)
                    page.wait_for_timeout(1500)
                    datos = page.evaluate(LEER_FAMILIA)
                if not datos or not datos["titular"]:
                    captura_error(page, salida, cedula)
                    return "ERROR", "la consulta no trae datos del titular (ni Registro Civil ni Datos Generales)"
                familiares = elegir_familiares(datos["familia"])
                resultados[cedula] = {"titular": datos["titular"], "familiares": familiares}
                conyuges = sum(f["parentesco"] == "CONYUGE" for f in familiares)
                t = datos["titular"]
                origen = f" (familia de {datos['fuente_familia']})" if datos["fuente_familia"] else " (sin árbol familiar)"
                return "OK", (f"{t['nombre']} · {t['edad']} años · {t['estado_civil']} · "
                              f"cónyuge: {conyuges} · hijos: {len(familiares) - conyuges}{origen}")
            except Exception as e:
                captura_error(page, salida, cedula)
                return "ERROR", str(e).splitlines()[0]
            finally:
                page.wait_for_timeout(1000)  # pausa para no saturar el servidor

        # Carpeta nueva en cada trabajo; cada cédula se consulta una vez
        log_path = con_reintentos(list(dict.fromkeys(cedulas)), lambda c: c, intentar, salida, al_avanzar,
                                  extension="sin-archivo", cancelado=cancelado)
        browser.close()

    guardar_excel(cedulas, resultados, salida / "familia.xlsx")  # en el orden del Excel, repetidas incluidas
    return log_path


def main():
    ap = argparse.ArgumentParser(description="Titular, cónyuge e hijos de una lista de cédulas desde Mina")
    ap.add_argument("excel", help="Archivo .xlsx con las cédulas")
    ap.add_argument("--columna", help="Nombre de la columna con las cédulas (por defecto 'cedula' o la primera)")
    ap.add_argument("--salida", default="familia_mina", help="Carpeta donde guardar el resultado")
    args = ap.parse_args()

    if os.environ.get("MINA_AUTORIZADO", "").lower() not in ("si", "sí", "true", "1"):
        sys.exit("Falta MINA_AUTORIZADO=si en el .env.")
    cedulas = leer_cedulas(args.excel, args.columna)
    if not cedulas:
        sys.exit("No se encontraron cédulas en el Excel.")
    procesar(cedulas, args.salida)
    print(f"Listo. Resultado en {Path(args.salida) / 'familia.xlsx'}")


if __name__ == "__main__":
    main()
