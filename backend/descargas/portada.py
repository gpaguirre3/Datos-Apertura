import argparse
import sys
from pathlib import Path

from . import consolidado
from . import descargar_certificados as isspol

CONSULTAS = consolidado.PORTADA
TODOS = "portada_todos.pdf"

carpeta = consolidado.carpeta


def procesar(cedulas, salida, al_avanzar=None, cancelado=None):
    personas = [(c, "") for c in cedulas]
    return consolidado.procesar(personas, salida, al_avanzar=al_avanzar, cancelado=cancelado,
                                consultas=CONSULTAS, nombre_todos=TODOS)


def main():
    ap = argparse.ArgumentParser(
        description="Mina, Aduana y Procesos judiciales por cédula, en un PDF con las tres capturas")
    ap.add_argument("excel", help="Archivo .xlsx con una columna de cédulas")
    ap.add_argument("--salida", default="portada", help="Carpeta donde guardar los PDF")
    args = ap.parse_args()

    cedulas = isspol.leer_cedulas(args.excel)
    if not cedulas:
        sys.exit("No se encontraron cédulas en el Excel.")
    print(f"{len(cedulas)} cédulas. PDF en: {Path(args.salida).resolve()}")
    print(f"Listo. Resumen en {procesar(cedulas, args.salida)}")


if __name__ == "__main__":
    main()
