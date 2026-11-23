import argparse
import csv
import io
import re
import sys
from copy import copy
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

MONEDA = "DOLARES DE LOS ESTADOS UNIDOS DE AMÉRICA"
LIMITE = 10 ** 12  
COLUMNAS = ("monto", "montos", "valor", "valores", "cantidad", "importe", "total")

HASTA_29 = ("", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE", "DIEZ",
            "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE", "DIECISÉIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE",
            "VEINTE", "VEINTIÚN", "VEINTIDÓS", "VEINTITRÉS", "VEINTICUATRO", "VEINTICINCO", "VEINTISÉIS",
            "VEINTISIETE", "VEINTIOCHO", "VEINTINUEVE")
DECENAS = ("", "", "", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA")
CENTENAS = ("", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS",
            "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS")


def _centenas(n):
    if n == 100:
        return "CIEN"
    c, resto = divmod(n, 100)
    if resto < 30:
        cola = HASTA_29[resto]
    else:
        d, u = divmod(resto, 10)
        cola = DECENAS[d] + (f" Y {HASTA_29[u]}" if u else "")
    return " ".join(p for p in (CENTENAS[c], cola) if p)


def _miles(n):
    m, resto = divmod(n, 1000)
    inicio = "MIL" if m == 1 else f"{_centenas(m)} MIL" if m else ""
    return " ".join(p for p in (inicio, _centenas(resto)) if p)


def entero_a_letras(n):
    if n == 0:
        return "CERO"
    millones, resto = divmod(n, 10 ** 6)
    inicio = "UN MILLÓN" if millones == 1 else f"{_miles(millones)} MILLONES" if millones else ""
    return " ".join(p for p in (inicio, _miles(resto)) if p)


def monto_a_letras(monto):
    monto = monto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if monto < 0:
        raise ValueError("monto negativo")
    if monto >= LIMITE:
        raise ValueError("monto demasiado grande")
    entero = int(monto)
    centavos = int((monto - entero) * 100)
    return f"{entero_a_letras(entero)} CON {centavos:02d}/100 {MONEDA}"


def leer_monto(valor):
    if isinstance(valor, bool):
        raise ValueError("no es un monto")
    if isinstance(valor, (int, float, Decimal)):
        try:
            return Decimal(str(valor))
        except InvalidOperation:
            raise ValueError("no es un monto")

    texto = re.sub(r"[\s $]|usd", "", str(valor), flags=re.I)
    if not re.fullmatch(r"-?\d[\d.,]*", texto):
        raise ValueError("no es un monto")
    comas, puntos = texto.count(","), texto.count(".")
    if comas and puntos:  # 2.356,84 o 2,356.84: el último separador es el decimal
        ultimo = max(texto.rfind(","), texto.rfind("."))
        entero, decimales = texto[:ultimo], texto[ultimo + 1:]
    elif comas + puntos == 1:  # 2356,84 es decimal; 2.356 o 2,356 (3 dígitos) es de miles
        entero, decimales = re.split(r"[.,]", texto)
        if len(decimales) == 3:
            entero, decimales = entero + decimales, "0"
    elif comas + puntos > 1:  # 1.234.567: todos son de miles
        entero, decimales = texto, "0"
    else:
        return Decimal(texto)

    if not re.fullmatch(r"-?\d{1,3}([.,]\d{3})*|-?\d+", entero) or not re.fullmatch(r"\d{1,2}", decimales):
        raise ValueError("no es un monto")
    return Decimal(re.sub(r"[.,]", "", entero) + "." + decimales)


def _es_monto(valor):
    try:
        leer_monto(valor)
        return True
    except ValueError:
        return False


def leer_montos(ruta_excel, columna=None):
    ws = load_workbook(ruta_excel, read_only=True, data_only=True).active
    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        return []

    encabezado = [str(c or "").strip().lower() for c in filas[0]]
    claves = ((columna or "").strip().lower(),) if columna else COLUMNAS
    idx = next((i for i, n in enumerate(encabezado) if n in claves), None)
    tiene_encabezado = idx is not None or not _es_monto(filas[0][0])
    if idx is None:
        idx = 0

    return [(n, fila[idx]) for n, fila in enumerate(filas, 1)
            if n > tiene_encabezado and idx < len(fila) and fila[idx] not in (None, "")]


def excel_con_letras(contenido, letras, destino):
    wb = load_workbook(io.BytesIO(contenido))
    ws = wb.active
    nueva = ws.max_column + 1
    if 1 not in letras and any(c.value not in (None, "") for c in ws[1]):  # la fila 1 es encabezado
        ws.cell(1, nueva, "letras").font = copy(ws.cell(1, 1).font)
    for fila, texto in letras.items():
        ws.cell(fila, nueva, texto)
    ws.column_dimensions[ws.cell(1, nueva).column_letter].width = 100
    wb.save(destino)


def procesar(items, salida, al_avanzar=None, cancelado=None, contenido=None, nombre_excel="montos"):
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    por_fila = {}

    wb = Workbook()
    ws = wb.active
    ws.title = "Montos"
    ws.append(["monto", "letras"])
    for celda in ws[1]:
        celda.font = Font(bold=True)
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 100

    with open(salida / "resultado.csv", "w", newline="", encoding="utf-8-sig") as f:
        log = csv.writer(f)
        log.writerow(["fila", "monto", "estado", "detalle"])
        for fila, valor in items:
            try:
                monto = leer_monto(valor)
                letras = monto_a_letras(monto)
            except ValueError as e:
                ws.append([str(valor), ""])
                estado, detalle, mostrar = "ERROR", str(e), str(valor)
            else:
                ws.append([float(monto), letras])
                ws.cell(ws.max_row, 1).number_format = "#,##0.00"
                mostrar = f"{monto.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}".replace(".", ",")
                estado, detalle = "OK", letras
                por_fila[fila] = letras
            log.writerow([fila, mostrar, estado, detalle])
            if al_avanzar:
                al_avanzar(mostrar, estado, detalle, clave=fila)

    wb.save(salida / "montos_letras.xlsx")
    if contenido:
        excel_con_letras(contenido, por_fila, salida / f"{nombre_excel}_con_letras.xlsx")
    return salida / "resultado.csv"


def main():
    ap = argparse.ArgumentParser(description="Convierte a letras los montos de un Excel")
    ap.add_argument("excel", help="Archivo .xlsx con los montos")
    ap.add_argument("--columna", help="Nombre de la columna con los montos (por defecto monto/valor/total o la primera)")
    ap.add_argument("--salida", default="montos_letras", help="Carpeta donde guardar el resultado")
    args = ap.parse_args()

    items = leer_montos(args.excel, args.columna)
    if not items:
        sys.exit("No se encontraron montos en el Excel.")
    procesar(items, args.salida)
    print(f"Listo. Resultado en {Path(args.salida) / 'montos_letras.xlsx'}")

if __name__ == "__main__":
    main()
