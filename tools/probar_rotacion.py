"""
Corre el recalculo de rotacion sin interfaz.

    python3 tools/probar_rotacion.py --data /ruta/DATOS --data2 /ruta/DATOS2 \
        --zip /ruta/ZIP --sucursal 1 [--meses 24] [--ri-es-venta]

Es el equivalente de `DO calcular_rotacion WITH 24, .T.` desde el ERP.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Parametros  # noqa: E402
from app.rotacion import OpcionesRotacion, calcular_rotacion  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--data2", default="")
    parser.add_argument("--zip", dest="zip", default="")
    parser.add_argument("--sucursal", default="1")
    parser.add_argument("--meses", type=int, default=24)
    parser.add_argument("--sin-pendrive", action="store_true")
    parser.add_argument("--sin-remoto", action="store_true")
    parser.add_argument(
        "--ri-es-venta", action="store_true",
        help="Cuenta los remitos internos como venta (comportamiento actual del ERP)",
    )
    args = parser.parse_args()

    parametros = Parametros(
        carpeta_datos=args.data,
        carpeta_datos2=args.data2,
        carpeta_zip=args.zip,
        sucursal=args.sucursal,
    )
    opciones = OpcionesRotacion(
        meses=args.meses,
        incluir_pendrive=not args.sin_pendrive,
        incluir_remoto=not args.sin_remoto,
        remitos_internos_son_venta=args.ri_es_venta,
    )

    def progreso(texto: str, porcentaje: int) -> None:
        print(f"  [{porcentaje:>3}%] {texto}", file=sys.stderr)

    resultado = calcular_rotacion(parametros, opciones, progreso)

    print(resultado.texto_informe())
    if not resultado.ok:
        print("\nNO SE GENERO LA TABLA:")
        print(resultado.mensaje)
        return 1

    print(f"\nDuracion: {resultado.duracion:.2f}s")
    if resultado.ruta_informe:
        print(f"Informe : {resultado.ruta_informe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
